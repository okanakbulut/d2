
import re
import types
import typing
from enum import Enum
from typing import Any, ClassVar, Generic, Self, TypeVar, cast, overload

import pypika
import pypika.analytics
import pypika.enums
import pypika.functions
import pypika.terms
from pypika.utils import format_alias_sql, format_quotes

from .filter import Filter, AnyFilter
from .model import FieldDef, ForeignKey, TableMeta
from .dialect import Dialect, PostgresDialect
from .query import InsertQuery, UpdateQuery, DeleteQuery, JoinClause


class JsonMode(str, Enum):
    DECODED = "decoded"
    RAW = "raw"


_QUERY_STATE_KEYS: tuple[str, ...] = (
    "__columns__",
    "__filters__",
    "__orderings__",
    "__row_limit__",
    "__row_offset__",
    "__is_distinct__",
    "__joins__",
    "__group_bys__",
    "__havings__",
    "__alias__",
    "__inner__",
    "__union_left__",
    "__union_right__",
    "__set_op__",
    "__ctes__",
    "__recursive__",
    "__prefetches__",
    "__as_json__",
)

_DEFAULTS: dict[str, Any] = {
    "__columns__": (),
    "__filters__": (),
    "__orderings__": (),
    "__row_limit__": None,
    "__row_offset__": None,
    "__is_distinct__": False,
    "__joins__": (),
    "__group_bys__": (),
    "__havings__": (),
    "__alias__": None,
    "__inner__": None,
    "__union_left__": None,
    "__union_right__": None,
    "__set_op__": "",
    "__ctes__": (),
    "__recursive__": False,
    "__prefetches__": (),
    "__as_json__": None,
}


class NamespacedField(pypika.Field):
    """pypika Field that always renders as [alias_or_table].column."""

    def get_sql(self, **kwargs: Any) -> str:
        with_alias = kwargs.pop("with_alias", False)
        kwargs.pop("with_namespace", None)
        quote_char = kwargs.pop("quote_char", None)

        field_sql = format_quotes(self.name, quote_char)

        if self.table:
            tbl = cast(pypika.Table, self.table)
            ref_name = getattr(tbl, "alias", None) or tbl.get_table_name()
            table_sql = format_quotes(ref_name, quote_char)
            field_sql = f"{table_sql}.{field_sql}"

        field_alias = getattr(self, "alias", None)
        if with_alias:
            return format_alias_sql(field_sql, field_alias, quote_char=quote_char, **kwargs)
        return field_sql

T = TypeVar("T")


class Field(Generic[T]):
    column_name: str
    python_type: type[T]
    field_def: FieldDef
    pika_field: pypika.Field

    def __init__(
        self,
        column_name: str,
        python_type: type[T],
        field_def: FieldDef,
        pika_field: pypika.Field,
    ) -> None:
        object.__setattr__(self, "column_name", column_name)
        object.__setattr__(self, "python_type", python_type)
        object.__setattr__(self, "field_def", field_def)
        object.__setattr__(self, "pika_field", pika_field)

    @overload
    def __get__(self, obj: None, objtype: type) -> "Field[T]": ...
    @overload
    def __get__(self, obj: object, objtype: type) -> T: ...
    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return self

    def __eq__(self, other: Any) -> Any:
        from .filter import Filter
        if isinstance(other, Field):
            return Filter(field=self, value=other, op="col_eq")
        return Filter(field=self, value=other)

    def __ne__(self, other: Any) -> Any:
        from .filter import Filter
        return Filter(field=self, value=other, op="ne")

    def __lt__(self, other: Any) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=other, op="lt")

    def __le__(self, other: Any) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=other, op="lte")

    def __gt__(self, other: Any) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=other, op="gt")

    def __ge__(self, other: Any) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=other, op="gte")

    def like(self, pattern: str) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=pattern, op="like")

    def ilike(self, pattern: str) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=pattern, op="ilike")

    def isin(self, values: list[Any]) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=tuple(values), op="in")

    def notin(self, values: list[Any]) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=tuple(values), op="notin")

    def isnull(self) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=None, op="null")

    def isnotnull(self) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=None, op="notnull")

    def between(self, lo: Any, hi: Any) -> Filter:
        from .filter import Filter
        return Filter(field=self, value=(lo, hi), op="between")

    def aliased(self, alias: str) -> "Field[T]":
        new = cast("Field[T]", Field.__new__(Field))
        object.__setattr__(new, "column_name", self.column_name)
        object.__setattr__(new, "python_type", self.python_type)
        object.__setattr__(new, "field_def", self.field_def)
        object.__setattr__(new, "pika_field", self.pika_field.as_(alias))
        return new

    def count(self, distinct: bool = False) -> "Field[int]":
        term = pypika.functions.Count(self.pika_field)
        if distinct:
            term = term.distinct()
        return _AggField(int, term)

    def sum(self) -> "Field[T]":
        return _AggField(self.python_type, pypika.functions.Sum(self.pika_field))

    def min(self) -> "Field[T]":
        return _AggField(self.python_type, pypika.functions.Min(self.pika_field))

    def max(self) -> "Field[T]":
        return _AggField(self.python_type, pypika.functions.Max(self.pika_field))

    def avg(self) -> "Field[float]":
        return _AggField(float, pypika.functions.Avg(self.pika_field))

    def coalesce(self, default: Any) -> "Field[T]":
        return _CoalesceField(self, default)

    def cast(self, sql_type: str) -> "Field[Any]":
        return _AggField(type(None), pypika.functions.Cast(self.pika_field, sql_type))

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        return self.pika_field

    def desc(self) -> "_SortedField[T]":
        return _SortedField(self, descending=True)

    def asc(self) -> "_SortedField[T]":
        return _SortedField(self, descending=False)

    def over(self, *partition_by: "Field[Any]") -> "WindowSpec":
        return WindowSpec(pypika.analytics.RowNumber(), partition_by, ())

    def __add__(self, other: Any) -> "Field[Any]":
        return _ArithField(self, "+", other)

    def __sub__(self, other: Any) -> "Field[Any]":
        return _ArithField(self, "-", other)

    def __mul__(self, other: Any) -> "Field[Any]":
        return _ArithField(self, "*", other)

    def __truediv__(self, other: Any) -> "Field[Any]":
        return _ArithField(self, "/", other)

    def __hash__(self) -> int:
        return hash(self.column_name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.column_name!r})"

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"cannot set '{name}' on {type(self).__name__}")


class _ArithField(Field[Any]):
    _left: Field[Any]
    _op: str
    _right: Any

    def __init__(self, left: Field[Any], op: str, right: Any) -> None:
        object.__setattr__(self, "column_name", left.column_name)
        object.__setattr__(self, "python_type", left.python_type)
        object.__setattr__(self, "field_def", left.field_def)
        object.__setattr__(self, "pika_field", left.pika_field)
        object.__setattr__(self, "_left", left)
        object.__setattr__(self, "_op", op)
        object.__setattr__(self, "_right", right)

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        left_term = self._left.to_column(params, dialect)
        right = self._right
        op = self._op
        if isinstance(right, Field):
            right_term = right.pika_field
        else:
            params.append(right)
            right_term = pypika.terms.Parameter(dialect.placeholder(len(params)))
        ops: dict[str, Any] = {"+": left_term + right_term, "-": left_term - right_term,
                               "*": left_term * right_term, "/": left_term / right_term}
        return ops[op]



class _AggField(Field[T]):
    """A Field backed by a pypika aggregate (or scalar) term."""

    def __init__(self, python_type: type[T], pika_term: pypika.terms.Term) -> None:
        object.__setattr__(self, "column_name", "")
        object.__setattr__(self, "python_type", python_type)
        object.__setattr__(self, "field_def", FieldDef())
        object.__setattr__(self, "pika_field", pika_term)

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        return self.pika_field

    def aliased(self, alias: str) -> Field[T]:
        return _AggField(self.python_type, self.pika_field.as_(alias))

    def over(self, *partition_by: "Field[Any]") -> "WindowSpec":
        fn_name = getattr(self.pika_field, "name", "").upper()
        analytic_cls = _ANALYTIC_FN_MAP.get(fn_name, pypika.analytics.RowNumber)
        args = getattr(self.pika_field, "args", [])
        analytic_fn = analytic_cls(*args)
        return WindowSpec(analytic_fn, partition_by, ())


class _CoalesceField(Field[T]):
    """COALESCE(col, default) — default is bound as a parameter at build time."""

    _source: Field[T]
    _default: Any

    def __init__(self, source: Field[T], default: Any) -> None:
        object.__setattr__(self, "column_name", source.column_name)
        object.__setattr__(self, "python_type", source.python_type)
        object.__setattr__(self, "field_def", source.field_def)
        object.__setattr__(self, "pika_field", source.pika_field)
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_default", default)

    def aliased(self, alias: str) -> Field[T]:
        source: Field[T] = object.__getattribute__(self, "_source")
        default: Any = object.__getattribute__(self, "_default")
        new = _CoalesceField(source, default)
        object.__setattr__(new, "_alias", alias)
        return new

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        default: Any = object.__getattribute__(self, "_default")
        source: Field[Any] = object.__getattribute__(self, "_source")
        params.append(default)
        default_term = pypika.terms.Parameter(dialect.placeholder(len(params)))
        term = pypika.functions.Coalesce(source.pika_field, default_term)
        alias = getattr(self, "_alias", None)
        if alias:
            return term.as_(alias)
        return term


_ANALYTIC_FN_MAP: dict[str, type] = {
    "AVG":   pypika.analytics.Avg,
    "SUM":   pypika.analytics.Sum,
    "MIN":   pypika.analytics.Min,
    "MAX":   pypika.analytics.Max,
    "COUNT": pypika.analytics.Count,
}


class _SortedField(Field[T]):
    """A Field annotated with a sort direction; produced by Field.desc() / Field.asc()."""

    descending: bool

    def __init__(self, source: "Field[T]", descending: bool) -> None:
        object.__setattr__(self, "column_name", source.column_name)
        object.__setattr__(self, "python_type", source.python_type)
        object.__setattr__(self, "field_def", source.field_def)
        object.__setattr__(self, "pika_field", source.pika_field)
        object.__setattr__(self, "descending", descending)


class WindowSpec:
    """Intermediate produced by Field.over(); chain .order_by() then finalize with .aliased()."""

    def __init__(
        self,
        analytic_fn: Any,
        partition: "tuple[Field[Any], ...]",
        orderings: "tuple[Field[Any], ...]",
    ) -> None:
        self._analytic_fn = analytic_fn
        self._partition = partition
        self._orderings = orderings

    def order_by(self, *fields: "Field[Any]") -> "WindowSpec":
        return WindowSpec(self._analytic_fn, self._partition, self._orderings + fields)

    def aliased(self, alias: str) -> "Field[Any]":
        pika_partitions = [f.pika_field for f in self._partition]
        term = self._analytic_fn.over(*pika_partitions)
        for f in self._orderings:
            if isinstance(f, _SortedField):
                order = pypika.enums.Order.desc if f.descending else pypika.enums.Order.asc
                term = term.orderby(f.pika_field, order=order)
            else:
                term = term.orderby(f.pika_field)
        return _AggField(type(None), term.as_(alias))


class _RawTerm(pypika.terms.Term):
    """A pypika Term that emits a pre-built SQL string verbatim."""

    def __init__(self, sql: str) -> None:
        super().__init__(alias=None)
        self._sql = sql

    def get_sql(self, **kwargs: Any) -> str:
        return self._sql


class _ExcludedTerm(pypika.terms.Term):
    """Renders as EXCLUDED."column" — EXCLUDED is a keyword, not a quoted table name."""

    def __init__(self, column_name: str) -> None:
        super().__init__(alias=None)
        self._col = column_name

    def get_sql(self, **kwargs: Any) -> str:
        quote_char = kwargs.get("quote_char", None)
        col = format_quotes(self._col, quote_char)
        return f"EXCLUDED.{col}"


def excluded(proxy: "Field[T]") -> "Field[T]":
    """Clone a FieldProxy that renders as EXCLUDED."column" in ON CONFLICT DO UPDATE."""
    new: Field[T] = Field.__new__(type(proxy))
    object.__setattr__(new, "column_name", proxy.column_name)
    object.__setattr__(new, "python_type", proxy.python_type)
    object.__setattr__(new, "field_def", proxy.field_def)
    object.__setattr__(new, "pika_field", _ExcludedTerm(proxy.column_name))
    return new


Column = Field  # alias


class PrimaryKey(Field[T]):
    pass


class Unique(Field[T]):
    pass


class Index(Field[T]):
    pass


_FIELD_FLAGS: dict[type, dict[str, bool]] = {
    PrimaryKey: {"primary_key": True},
    Unique: {"unique": True},
    Index: {"index": True},
    Field: {},
}


def _infer_table_name(class_name: str) -> str:
    name = re.sub(r"Model$", "", class_name)
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return name


def _infer_schema(module: str) -> str | None:
    parts = module.split(".")
    try:
        idx = parts.index("models")
        return parts[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def _parse_fields(model: type) -> list[tuple[str, type, FieldDef, type[Field[Any]]]]:
    hints = typing.get_type_hints(model, include_extras=True)
    result: list[tuple[str, type, FieldDef, type[Field[Any]]]] = []

    for attr_name, hint in hints.items():
        if attr_name.startswith("_"):
            continue

        origin = typing.get_origin(hint)
        nullable = False
        if origin is not None and isinstance(origin, type) and issubclass(origin, Field):
            args = typing.get_args(hint)
            inner: Any = args[0] if args else type(None)
            inner_origin = typing.get_origin(inner)
            if inner_origin is typing.Union or inner_origin is types.UnionType:
                union_args = [a for a in typing.get_args(inner) if a is not type(None)]
                if len(union_args) != len(typing.get_args(inner)):
                    nullable = True
                inner = union_args[0] if union_args else type(None)
            python_type: type = inner
            field_cls: type[Field[Any]] = cast("type[Field[Any]]", origin)
        elif isinstance(hint, type) and issubclass(hint, Field):
            python_type = type(None)
            field_cls = cast("type[Field[Any]]", hint)
        else:
            continue

        base_flags = _FIELD_FLAGS.get(field_cls, {})
        primary_key = base_flags.get("primary_key", False)
        unique = base_flags.get("unique", False)
        index = base_flags.get("index", False)
        db_default = False
        col_name_override: str | None = None
        fk: ForeignKey | None = None

        class_default = vars(model).get(attr_name)
        if isinstance(class_default, FieldDef):
            db_default = class_default.db_default
            col_name_override = class_default.name
            if class_default.unique:
                unique = True
            if class_default.index:
                index = True
            fk = class_default.fk

        fd = FieldDef(
            primary_key=primary_key,
            unique=unique,
            index=index,
            db_default=db_default,
            name=col_name_override,
            nullable=nullable,
            fk=fk,
        )
        result.append((attr_name, python_type, fd, field_cls))

    return result


def _setup_table(cls: Any) -> None:
    meta: TableMeta | None = getattr(cls, "__meta__", None)
    table_name = (meta.table if meta and meta.table else None) or _infer_table_name(cls.__name__)
    schema_name = (meta.schema if meta and meta.schema else None) or _infer_schema(getattr(cls, "__module__", "") or "")

    pika_table = pypika.Table(table_name, schema=schema_name) if schema_name else pypika.Table(table_name)

    fields = _parse_fields(cls)
    field_proxies: list[Field[Any]] = []

    for attr_name, python_type, fd, field_cls in fields:
        col_name = fd.name if fd.name else attr_name
        proxy = field_cls(col_name, python_type, fd, NamespacedField(col_name, table=pika_table))
        setattr(cls, attr_name, proxy)
        field_proxies.append(proxy)

    cls.__table__ = pika_table
    cls.__fields__ = tuple(field_proxies)

    from .migrations.registry import _register
    _register(cls)


class NormMeta(type):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "NormMeta":
        view_query = kwargs.pop("query", None)
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if "__table__" not in namespace and any(isinstance(b, NormMeta) for b in bases):
            _setup_table(cls)
            if view_query is not None:
                _validate_view_columns(cls, view_query)
                cls.__view_query__ = view_query
        return cls


def _validate_view_columns(cls: type, query: Any) -> None:
    """Cross-validate that View body annotations match the query's columns."""
    query_cols = getattr(query, "__columns__", ()) or ()
    body_fields = [
        (f.column_name, f.python_type) for f in getattr(cls, "__fields__", ())
    ]
    for idx, body in enumerate(body_fields):
        if idx >= len(query_cols):
            raise TypeError(
                f"View {cls.__name__!r}: column {body[0]!r} is not present in the query"
            )
        qcol = query_cols[idx]
        qname = getattr(qcol.pika_field, "alias", None) or qcol.column_name
        qtype = qcol.python_type
        if body[0] != qname:
            raise TypeError(
                f"View {cls.__name__!r}: column {body[0]!r} at position {idx} "
                f"does not match query column {qname!r}"
            )
        if body[1] is not qtype:
            raise TypeError(
                f"View {cls.__name__!r}: column {body[0]!r} has type "
                f"{body[1].__name__!r} but query column has type {qtype.__name__!r}"
            )
    if len(body_fields) != len(query_cols):
        extra = query_cols[len(body_fields)]
        ename = getattr(extra.pika_field, "alias", None) or extra.column_name
        raise TypeError(
            f"View {cls.__name__!r}: query column {ename!r} is not declared on the View body"
        )


class Entity(metaclass=NormMeta):
    """Base for all norm-managed database objects. Do not use directly — subclass Table or View."""

    __table__: ClassVar[pypika.Table]
    __fields__: ClassVar[tuple[Field[Any], ...]]

    # Query state defaults — inherited by all subclasses and overridden per-clone
    __columns__: ClassVar[tuple[Field[Any], ...]] = ()
    __filters__: ClassVar[tuple[Filter, ...]] = ()
    __orderings__: ClassVar[tuple[tuple[Field[Any], bool], ...]] = ()
    __row_limit__: ClassVar[int | None] = None
    __row_offset__: ClassVar[int | None] = None
    __is_distinct__: ClassVar[bool] = False
    __joins__: ClassVar[tuple[JoinClause, ...]] = ()
    __group_bys__: ClassVar[tuple[Field[Any], ...]] = ()
    __havings__: ClassVar[tuple[AnyFilter, ...]] = ()
    __alias__: ClassVar[str | None] = None
    __inner__: ClassVar[Any] = None
    __union_left__: ClassVar[Any] = None
    __union_right__: ClassVar[Any] = None
    __set_op__: ClassVar[str] = ""
    __ctes__: ClassVar[tuple[Any, ...]] = ()
    __recursive__: ClassVar[bool] = False
    __prefetches__: ClassVar[tuple[Any, ...]] = ()
    __as_json__: ClassVar[JsonMode | None] = None

    @classmethod
    def clone(cls) -> type[Self]:
        """Create a shallow copy of this entity type, copying all query state."""
        ns: dict[str, Any] = {
            "__table__": cls.__table__,
            "__fields__": cls.__fields__,
        }
        for key in _QUERY_STATE_KEYS:
            ns[key] = getattr(cls, key, _DEFAULTS[key])
        for attr, val in vars(cls).items():
            if isinstance(val, Field):
                ns[attr] = val
        return cast(type[Self], NormMeta(cls.__name__, (cls,), ns))

    @classmethod
    def aliased(cls, alias: str) -> type[typing.Any]:
        """Return a renamed view of this entity.

        On a plain entity (no query state): creates a real table alias for self-joins.
        On a query chain (has columns or union): creates a subquery/CTE alias.
        """
        alias_table = pypika.Table(alias)
        union_left = getattr(cls, "__union_left__", None)
        has_query = union_left is not None or bool(getattr(cls, "__columns__", ()))

        ns: dict[str, Any] = {"__table__": alias_table, "__fields__": ()}
        for key in _QUERY_STATE_KEYS:
            ns[key] = _DEFAULTS[key]
        ns["__alias__"] = alias

        if has_query:
            # Subquery / CTE alias: store the original as __inner__ and remap projected columns
            ns["__inner__"] = cls
            if union_left is not None:
                source_cols: tuple[Field[Any], ...] = (
                    getattr(union_left, "__columns__", ()) or getattr(union_left, "__fields__", ())
                )
            else:
                source_cols = cls.__columns__
            new_fields: list[Field[Any]] = []
            for col in source_cols:
                col_alias = getattr(col.pika_field, "alias", None)
                name: str = col_alias or col.column_name
                if not name:
                    continue
                pika = NamespacedField(name, table=alias_table)
                proxy = Field(name, col.python_type, col.field_def, pika)
                ns[name] = proxy
                new_fields.append(proxy)
            ns["__fields__"] = tuple(new_fields)
        else:
            # Real table alias: remap all field proxies to use the aliased pika table
            orig_table = cls.__table__
            real_name: str = getattr(orig_table, "_table_name", "")
            schema_obj: Any = getattr(orig_table, "_schema", None)
            pika_table = pypika.Table(real_name, schema=schema_obj).as_(alias)
            ns["__table__"] = pika_table
            ns["__inner__"] = None
            new_fields = []
            for attr, val in vars(cls).items():
                if isinstance(val, Field):
                    fval = cast(Field[Any], val)
                    new_pika = NamespacedField(fval.column_name, table=pika_table)
                    new_proxy: Field[Any] = type(fval)(fval.column_name, fval.python_type, fval.field_def, new_pika)
                    ns[attr] = new_proxy
                    new_fields.append(new_proxy)
            ns["__fields__"] = tuple(new_fields)

        return cast(type[Self], NormMeta(cls.__name__, (cls,), ns))


class Selectable(Entity):
    """Mixin that adds SELECT and query-building capability. Inherit via Table or View."""

    @classmethod
    def select(cls, *proxies: Field[Any]) -> "type[Self]":
        q = cls.clone()
        q.__columns__ = proxies
        return q

    @classmethod
    def select_all(cls) -> type[Self]:
        q = cls.clone()
        q.__columns__ = cls.__fields__
        return q

    @classmethod
    def where(cls, filter: Filter) -> type[Self]:
        q = cls.clone()
        q.__filters__ = cls.__filters__ + (filter,)
        return q

    @classmethod
    def order_by(cls, *fields: Field[Any], desc: bool = False) -> type[Self]:
        q = cls.clone()
        q.__orderings__ = cls.__orderings__ + tuple((f, desc) for f in fields)
        return q

    @classmethod
    def limit(cls, n: int) -> type[Self]:
        q = cls.clone()
        q.__row_limit__ = n
        return q

    @classmethod
    def offset(cls, n: int) -> type[Self]:
        q = cls.clone()
        q.__row_offset__ = n
        return q

    @classmethod
    def distinct(cls) -> type[Self]:
        q = cls.clone()
        q.__is_distinct__ = True
        return q

    @classmethod
    def join(cls, other: type[Selectable], *, on: AnyFilter) -> type[Self]:
        from .query import JoinClause
        table = other if getattr(other, "__inner__", None) is not None else other.__table__
        q = cls.clone()
        q.__joins__ = cls.__joins__ + (JoinClause(table, on, "inner"),)
        return q

    @classmethod
    def left_join(cls, other: type[Selectable], *, on: AnyFilter) -> type[Self]:
        from .query import JoinClause
        table = other if getattr(other, "__inner__", None) is not None else other.__table__
        q = cls.clone()
        q.__joins__ = cls.__joins__ + (JoinClause(table, on, "left"),)
        return q

    @classmethod
    def right_join(cls, other: type[Selectable], *, on: AnyFilter) -> type[Self]:
        from .query import JoinClause
        table = other if getattr(other, "__inner__", None) is not None else other.__table__
        q = cls.clone()
        q.__joins__ = cls.__joins__ + (JoinClause(table, on, "right"),)
        return q

    @classmethod
    def cross_join(cls, other: type[Selectable]) -> type[Self]:
        from .query import JoinClause
        table = other if getattr(other, "__inner__", None) is not None else other.__table__
        q = cls.clone()
        q.__joins__ = cls.__joins__ + (JoinClause(table, None, "cross"),)
        return q

    @classmethod
    def group_by(cls, *proxies: Field[Any]) -> type[Self]:
        q = cls.clone()
        q.__group_bys__ = cls.__group_bys__ + proxies
        return q

    @classmethod
    def having(cls, criterion: AnyFilter) -> type[Self]:
        q = cls.clone()
        q.__havings__ = cls.__havings__ + (criterion,)
        return q

    @classmethod
    def _make_set_op(cls, other: type[Selectable], op: str) -> type[Self]:
        ns: dict[str, Any] = {
            "__table__": cls.__table__,
            "__fields__": getattr(cls, "__columns__", ()) or cls.__fields__,
        }
        for key in _QUERY_STATE_KEYS:
            ns[key] = _DEFAULTS[key]
        ns["__union_left__"] = cls
        ns["__union_right__"] = other
        ns["__set_op__"] = op
        for attr, val in vars(cls).items():
            if isinstance(val, Field):
                ns[attr] = val
        return cast(type[Self], NormMeta(cls.__name__, (cls,), ns))

    @classmethod
    def union(cls, other: type[Selectable], *, all: bool = False) -> type[Self]:
        return cls._make_set_op(other, "UNION ALL" if all else "UNION")

    @classmethod
    def intersect(cls, other: type[Selectable]) -> type[Self]:
        return cls._make_set_op(other, "INTERSECT")

    @classmethod
    def exclude(cls, other: type[Selectable]) -> type[Self]:
        return cls._make_set_op(other, "EXCEPT")

    @classmethod
    def prefetch(cls, *children: "type[Any]") -> "type[Self]":
        q = cls.clone()
        q.__prefetches__ = cls.__prefetches__ + children
        return q

    @classmethod
    def json(cls, *, raw: bool = False) -> "type[Self]":
        q = cls.clone()
        q.__as_json__ = JsonMode.RAW if raw else JsonMode.DECODED
        return q

    @classmethod
    def as_scalar(cls) -> "Any":
        from .query import ScalarSubquery
        return ScalarSubquery(inner=cls)

    @classmethod
    def as_pypika(cls, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        pika_cols = [col.to_column(params, dialect) for col in cls.__columns__]
        for child in cls.__prefetches__:
            alias: str = child.__alias__
            inner: Any = child.__inner__
            inner_pika = inner.as_pypika(params, dialect, cte_names)
            inner_sql = inner_pika.get_sql(quote_char='"')
            if inner.__row_limit__ == 1:
                prefetch_sql = f"(SELECT row_to_json(t) FROM ({inner_sql}) t) AS \"{alias}\""
            else:
                prefetch_sql = f"(SELECT COALESCE(json_agg(t),'[]'::json) FROM ({inner_sql}) t) AS \"{alias}\""
            pika_cols.append(_RawTerm(prefetch_sql))
        q = pypika.Query.from_(cls.__table__).select(*pika_cols)
        if cls.__is_distinct__:
            q = q.distinct()
        for jc in cls.__joins__:
            q = jc.apply_to(q, params, dialect, cte_names)
        for f in cls.__filters__:
            q = q.where(f.to_pypika(params, dialect))
        for field, is_desc in cls.__orderings__:
            order = pypika.enums.Order.desc if is_desc else pypika.enums.Order.asc
            q = q.orderby(field.pika_field, order=order)
        for gb in cls.__group_bys__:
            q = q.groupby(gb.pika_field)
        for h in cls.__havings__:
            q = q.having(h.to_pypika(params, dialect))
        if cls.__row_limit__ is not None:
            q = q.limit(cls.__row_limit__)
        if cls.__row_offset__ is not None:
            q = q.offset(cls.__row_offset__)
        return q

    @classmethod
    def _build_set_op(cls, params: list[Any], dialect: Dialect) -> str:
        left_sql = cls.__union_left__.as_pypika(params, dialect).get_sql(quote_char='"')
        right_sql = cls.__union_right__.as_pypika(params, dialect).get_sql(quote_char='"')
        sql = f"({left_sql}) {cls.__set_op__} ({right_sql})"
        if cls.__orderings__:
            parts: list[str] = []
            for f, is_desc in cls.__orderings__:
                direction = "DESC" if is_desc else "ASC"
                parts.append(f'"{f.column_name}" {direction}')
            sql += " ORDER BY " + ", ".join(parts)
        if cls.__row_limit__ is not None:
            sql += f" LIMIT {cls.__row_limit__}"
        if cls.__row_offset__ is not None:
            sql += f" OFFSET {cls.__row_offset__}"
        return sql

    @classmethod
    def build(cls, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        if cls.__ctes__:
            return cls._build_with(dialect)
        params: list[Any] = []
        if cls.__as_json__ is not None and cls.__alias__ is not None and cls.__inner__ is not None:
            # .aliased("x").json(): wrap inner query in json_build_object(alias, json_agg(...))
            inner = cls.__inner__
            if getattr(inner, "__union_left__", None) is not None:
                inner_sql = inner._build_set_op(params, dialect)
            else:
                inner_sql = inner.as_pypika(params, dialect).get_sql(quote_char='"')
            alias = cls.__alias__
            cast = "::text" if cls.__as_json__ is JsonMode.RAW else ""
            sql = f"SELECT json_build_object('{alias}',COALESCE(json_agg(t),'[]'::json)){cast} FROM ({inner_sql}) t"
            return sql, tuple(params)
        if cls.__union_left__ is not None:
            sql = cls._build_set_op(params, dialect)
        else:
            sql = cls.as_pypika(params, dialect).get_sql(quote_char='"')
        if cls.__as_json__ is not None:
            cast = "::text" if cls.__as_json__ is JsonMode.RAW else ""
            sql = f"SELECT row_to_json(t){cast} FROM ({sql}) t"
        return sql, tuple(params)

    @classmethod
    def _build_with(cls, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        cte_names = frozenset(v.__alias__ for v in cls.__ctes__)
        cte_parts: list[str] = []
        for view in cls.__ctes__:
            inner = view.__inner__
            union_left = getattr(inner, "__union_left__", None)
            if union_left is not None:
                left_sql = union_left.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
                right_sql = inner.__union_right__.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
                union_kw = inner.__set_op__ or "UNION"
                body_sql = f"{left_sql} {union_kw} {right_sql}"
            else:
                body_sql = inner.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
            cte_parts.append(f'"{view.__alias__}" AS ({body_sql})')
        main_sql = cls.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
        prefix = "WITH RECURSIVE " if cls.__recursive__ else "WITH "
        return prefix + ", ".join(cte_parts) + " " + main_sql, tuple(params)


class Writable(Entity):
    """Mixin that adds INSERT/UPDATE/DELETE capability. Inherit via Table, not directly."""

    @classmethod
    def _default_columns(cls) -> frozenset[str]:
        return frozenset(
            f.column_name for f in cls.__fields__
            if f.field_def.db_default or f.field_def.primary_key
        )

    @classmethod
    def insert(cls, rows: "list[dict[str, Any]] | None" = None, *, exclude_defaults: bool = True, **kwargs: Any) -> InsertQuery:
        from .query import InsertQuery
        excluded = cls._default_columns() if exclude_defaults else frozenset[str]()
        if rows is not None:
            if not rows:
                raise ValueError("insert requires at least one row")
            filtered = [{k: v for k, v in row.items() if k not in excluded} for row in rows]
            first_cols = set(filtered[0].keys())
            if any(set(r.keys()) != first_cols for r in filtered[1:]):
                raise ValueError("all rows must have a consistent set of columns")
            return InsertQuery(source=cls.__table__, rows=tuple(filtered), is_many=True)
        row = {k: v for k, v in kwargs.items() if k not in excluded}
        return InsertQuery(source=cls.__table__, rows=(row,), is_many=False)

    @classmethod
    def update(cls, **assignments: Any) -> UpdateQuery:
        from .query import UpdateQuery
        col_assignments = tuple(
            (getattr(cls, attr).column_name, value)
            for attr, value in assignments.items()
        )
        return UpdateQuery(source=cls.__table__, assignments=col_assignments)

    @classmethod
    def delete(cls) -> DeleteQuery:
        from .query import DeleteQuery
        return DeleteQuery(source=cls.__table__)


class Table(Selectable, Writable):
    """Readable and writable database table."""


class View(Selectable):
    """Read-only database view or table."""
