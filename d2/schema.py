
import re
import types
import typing
from enum import Enum
from typing import Any, ClassVar, Generic, Self, TypeVar, cast, overload

import msgspec
import pypika
import pypika.analytics
import pypika.enums
import pypika.functions
import pypika.terms
from pypika.utils import format_alias_sql, format_quotes

from .filter import Filter, AnyFilter
from .model import FieldDef, TableMeta, INFER
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

    def aliased(self, alias: str) -> "Field[Any]":
        new = _ArithField(self._left, self._op, self._right)
        object.__setattr__(new, "_alias", alias)
        return new

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
        result = ops[op]
        alias = getattr(self, "_alias", None)
        if alias:
            return result.as_(alias)
        return result



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


class ForeignKey(Field[T]):
    pass


_FIELD_FLAGS: dict[type, dict[str, bool]] = {
    PrimaryKey: {},
    Unique: {"unique": True},
    Index: {"index": True},
    ForeignKey: {},
    Field: {},
}


def primary_key_field(model: type) -> "Field[Any] | None":
    """The model's PrimaryKey proxy, or None when it declares no primary key."""
    fields = cast("tuple[Field[Any], ...]", getattr(model, "__fields__", ()))
    return next((f for f in fields if isinstance(f, PrimaryKey)), None)


def _infer_table_name(class_name: str) -> str:
    name = re.sub(r"Model$", "", class_name)
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


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
        unique = base_flags.get("unique", False)
        index = base_flags.get("index", False)
        col_name_override: str | None = None
        references: type | None = None

        # PrimaryKey[Table] is not allowed — use a separate id and ForeignKey(unique=True)
        if issubclass(field_cls, PrimaryKey) and hasattr(python_type, "__fields__"):
            raise TypeError(
                f"{field_cls.__name__}[{python_type.__name__}] is not allowed. "
                "Use a separate id: PrimaryKey[int] and a ForeignKey with unique=True instead."
            )

        # ForeignKey[Model] — resolve the referenced model's PK type
        if issubclass(field_cls, ForeignKey) and hasattr(python_type, "__fields__"):
            referenced_model = python_type
            pk_proxy = primary_key_field(referenced_model)
            python_type = pk_proxy.python_type if pk_proxy else int
            references = referenced_model

        class_default = vars(model).get(attr_name)
        fd_default = class_default if isinstance(class_default, FieldDef) else None

        if fd_default is not None:
            col_name_override = fd_default.name
            if fd_default.unique:
                unique = True
            if fd_default.index:
                index = True

        fd = FieldDef(
            default=fd_default.default if fd_default is not None else None,
            unique=unique,
            index=index,
            name=col_name_override,
            nullable=nullable,
            references=references,
            on_delete=fd_default.on_delete if fd_default is not None else None,
            on_update=fd_default.on_update if fd_default is not None else None,
        )
        result.append((attr_name, python_type, fd, field_cls))

    return result


def _setup_table(cls: Any) -> None:
    meta: TableMeta | None = getattr(cls, "__meta__", None)
    table_name = (meta.table if meta and meta.table else None) or _infer_table_name(cls.__name__)
    if meta is None or meta.schema is INFER:
        schema_name = _infer_schema(getattr(cls, "__module__", "") or "") or "public"
    elif meta.schema is None:
        schema_name = None
    else:
        schema_name = meta.schema

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

    from .migrations.registry import register
    register(cls)


class D2Meta(type):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "D2Meta":
        view_query = kwargs.pop("query", None)
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if "__table__" not in namespace and any(isinstance(b, D2Meta) for b in bases):
            _setup_table(cls)
            if view_query is not None:
                _validate_view_columns(cls, view_query)
                setattr(cls, "__view_query__", view_query)
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


class Entity(metaclass=D2Meta):
    """Base for all d2-managed database objects. Do not use directly — subclass Table or View."""

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
        return cast(type[Self], D2Meta(cls.__name__, (cls,), ns))

    @classmethod
    def aliased(cls, alias: str) -> type[typing.Any]:
        """Return this table under another name, for a self-join.

        Naming a *query* is :meth:`Query.aliased`, which is a different job: it
        turns a query into a relation. That used to be this method's other half,
        reached when the entity carried query state -- but a query is no longer
        a subclass of its entity, so nothing arrives here with columns on it.
        """
        alias_table = pypika.Table(alias)
        ns: dict[str, Any] = {"__table__": alias_table, "__fields__": ()}
        for key in _QUERY_STATE_KEYS:
            ns[key] = _DEFAULTS[key]
        ns["__alias__"] = alias
        ns["__inner__"] = None

        orig_table = cls.__table__
        real_name: str = getattr(orig_table, "_table_name", "")
        schema_obj: Any = getattr(orig_table, "_schema", None)
        pika_table = pypika.Table(real_name, schema=schema_obj).as_(alias)
        ns["__table__"] = pika_table
        new_fields: list[Field[Any]] = []
        for attr, val in vars(cls).items():
            if isinstance(val, Field):
                fval = cast(Field[Any], val)
                new_pika = NamespacedField(fval.column_name, table=pika_table)
                new_proxy: Field[Any] = type(fval)(fval.column_name, fval.python_type, fval.field_def, new_pika)
                ns[attr] = new_proxy
                new_fields.append(new_proxy)
        ns["__fields__"] = tuple(new_fields)

        return cast(type[Self], D2Meta(cls.__name__, (cls,), ns))


class Query(msgspec.Struct, frozen=True):
    """A query under construction: which entity, and what has been said about it.

    Query state used to live in eighteen dunders on a *subclass* of the entity,
    so every builder step called ``Entity.clone()`` and built a whole new Python
    class through :class:`D2Meta`. Three quarters of a step's cost was
    ``type.__new__`` alone, and because ``clone()`` passed ``bases=(cls,)`` each
    step subclassed the one before it -- the MRO grew with the chain, so the
    eighth ``.where()`` on a twenty-field table cost half again what the first
    one did.

    Holding the state beside the entity rather than on a copy of it makes a step
    one ``msgspec.structs.replace``: about fifty times cheaper, and flat in the
    length of the chain. The entity is carried by reference, so the ``Field``
    proxies that used to be re-copied on every step never move at all.

    The dunder spellings survive as read-only properties, because an aliased
    relation is still a class (see :meth:`aliased`) and the same call sites read
    both -- a join target, a CTE body, a prefetch child. Inside this class the
    plain field is used; the properties are for everyone else.
    """

    entity: Any
    columns: tuple[Field[Any], ...] = ()
    filters: tuple[AnyFilter, ...] = ()
    orderings: tuple[tuple[Field[Any], bool], ...] = ()
    row_limit: int | None = None
    row_offset: int | None = None
    is_distinct: bool = False
    joins: tuple[JoinClause, ...] = ()
    group_bys: tuple[Field[Any], ...] = ()
    havings: tuple[AnyFilter, ...] = ()
    alias: str | None = None
    inner: Any = None
    union_left: Any = None
    union_right: Any = None
    set_op: str = ""
    ctes: tuple[Any, ...] = ()
    recursive: bool = False
    prefetches: tuple[Any, ...] = ()
    as_json: JsonMode | None = None

    # -- the dunder spellings, for call sites that also see alias classes -----

    @property
    def __table__(self) -> pypika.Table:
        return cast(pypika.Table, self.entity.__table__)

    @property
    def __fields__(self) -> tuple[Field[Any], ...]:
        # A set operation reports the columns of its left arm: that is what
        # `aliased()` remaps when a union is given a name.
        if self.union_left is not None:
            return self.union_left.__columns__ or self.union_left.__fields__
        return self.columns or cast(tuple[Field[Any], ...], self.entity.__fields__)

    @property
    def __columns__(self) -> tuple[Field[Any], ...]:
        return self.columns

    @property
    def __alias__(self) -> str | None:
        return self.alias

    @property
    def __inner__(self) -> Any:
        return self.inner

    @property
    def __union_left__(self) -> Any:
        return self.union_left

    @property
    def __union_right__(self) -> Any:
        return self.union_right

    @property
    def __set_op__(self) -> str:
        return self.set_op

    @property
    def __row_limit__(self) -> int | None:
        return self.row_limit

    @property
    def __row_offset__(self) -> int | None:
        return self.row_offset

    @property
    def __as_json__(self) -> JsonMode | None:
        return self.as_json

    @property
    def __filters__(self) -> tuple[AnyFilter, ...]:
        return self.filters

    @property
    def __orderings__(self) -> tuple[tuple[Field[Any], bool], ...]:
        return self.orderings

    @property
    def __joins__(self) -> tuple[JoinClause, ...]:
        return self.joins

    @property
    def __group_bys__(self) -> tuple[Field[Any], ...]:
        return self.group_bys

    @property
    def __havings__(self) -> tuple[AnyFilter, ...]:
        return self.havings

    @property
    def __is_distinct__(self) -> bool:
        return self.is_distinct

    @property
    def __ctes__(self) -> tuple[Any, ...]:
        return self.ctes

    @property
    def __recursive__(self) -> bool:
        return self.recursive

    @property
    def __prefetches__(self) -> tuple[Any, ...]:
        return self.prefetches

    # -- builder --------------------------------------------------------------

    def select(self, *proxies: Field[Any]) -> "Query":
        return msgspec.structs.replace(self, columns=proxies)

    def select_all(self) -> "Query":
        return msgspec.structs.replace(self, columns=self.entity.__fields__)

    def where(self, filter: AnyFilter) -> "Query":
        return msgspec.structs.replace(self, filters=self.filters + (filter,))

    def order_by(self, *fields: Field[Any], desc: bool = False) -> "Query":
        orderings: list[tuple[Field[Any], bool]] = []
        for f in fields:
            is_desc = f.descending if isinstance(f, _SortedField) else desc
            orderings.append((f, is_desc))
        return msgspec.structs.replace(self, orderings=self.orderings + tuple(orderings))

    def limit(self, n: int) -> "Query":
        return msgspec.structs.replace(self, row_limit=n)

    def offset(self, n: int) -> "Query":
        return msgspec.structs.replace(self, row_offset=n)

    def distinct(self) -> "Query":
        return msgspec.structs.replace(self, is_distinct=True)

    def _join(self, other: Any, on: AnyFilter | None, kind: str) -> "Query":
        table = other if getattr(other, "__inner__", None) is not None else other.__table__
        return msgspec.structs.replace(self, joins=self.joins + (JoinClause(table, on, kind),))

    def join(self, other: Any, *, on: AnyFilter) -> "Query":
        return self._join(other, on, "inner")

    def left_join(self, other: Any, *, on: AnyFilter) -> "Query":
        return self._join(other, on, "left")

    def right_join(self, other: Any, *, on: AnyFilter) -> "Query":
        return self._join(other, on, "right")

    def cross_join(self, other: Any) -> "Query":
        return self._join(other, None, "cross")

    def group_by(self, *proxies: Field[Any]) -> "Query":
        return msgspec.structs.replace(self, group_bys=self.group_bys + proxies)

    def having(self, criterion: AnyFilter) -> "Query":
        return msgspec.structs.replace(self, havings=self.havings + (criterion,))

    def prefetch(self, *children: Any) -> "Query":
        return msgspec.structs.replace(self, prefetches=self.prefetches + children)

    def json(self, *, raw: bool = False) -> "Query":
        return msgspec.structs.replace(self, as_json=JsonMode.RAW if raw else JsonMode.DECODED)

    def as_scalar(self) -> Any:
        from .query import ScalarSubquery

        return ScalarSubquery(inner=self)

    def _set_op(self, other: Any, op: str) -> "Query":
        # Everything else resets: the operands carry their own state, and what
        # is said after the operator (ORDER BY, LIMIT) applies to the result.
        return Query(entity=self.entity, union_left=self, union_right=other, set_op=op)

    def union(self, other: Any, *, all: bool = False) -> "Query":
        return self._set_op(other, "UNION ALL" if all else "UNION")

    def intersect(self, other: Any) -> "Query":
        return self._set_op(other, "INTERSECT")

    def exclude(self, other: Any) -> "Query":
        return self._set_op(other, "EXCEPT")

    def aliased(self, alias: str) -> type[Any]:
        """Name this query so it can be joined to, or used as a CTE.

        A class rather than another :class:`Query`, because the result is a
        *relation* and not a query under construction: callers reach through it
        for columns (``sub.total``), and a join target is detected by being a
        type. Naming a query happens once per query, so the class construction
        this costs is not on the builder's hot path.
        """
        alias_table = pypika.Table(alias)
        ns: dict[str, Any] = {"__table__": alias_table, "__fields__": ()}
        for key in _QUERY_STATE_KEYS:
            ns[key] = _DEFAULTS[key]
        ns["__alias__"] = alias
        ns["__inner__"] = self

        source_cols = self.__fields__
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
        return cast(type[Any], D2Meta(self.entity.__name__, (self.entity,), ns))

    # -- rendering ------------------------------------------------------------

    def as_pypika(self, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        pika_cols = [col.to_column(params, dialect) for col in self.columns]
        for child in self.prefetches:
            alias: str = child.__alias__
            inner: Any = child.__inner__
            inner_pika = inner.as_pypika(params, dialect, cte_names)
            inner_sql = inner_pika.get_sql(quote_char='"')
            if inner.__row_limit__ == 1:
                prefetch_sql = f"(SELECT row_to_json(t) FROM ({inner_sql}) t) AS \"{alias}\""
            else:
                prefetch_sql = f"(SELECT COALESCE(json_agg(t),'[]'::json) FROM ({inner_sql}) t) AS \"{alias}\""
            pika_cols.append(_RawTerm(prefetch_sql))
        q = pypika.Query.from_(self.entity.__table__).select(*pika_cols)
        if self.is_distinct:
            q = q.distinct()
        for jc in self.joins:
            q = jc.apply_to(q, params, dialect, cte_names)
        for f in self.filters:
            q = q.where(f.to_pypika(params, dialect))
        for field, is_desc in self.orderings:
            order = pypika.enums.Order.desc if is_desc else pypika.enums.Order.asc
            q = q.orderby(field.pika_field, order=order)
        for gb in self.group_bys:
            q = q.groupby(gb.pika_field)
        for h in self.havings:
            q = q.having(h.to_pypika(params, dialect))
        if self.row_limit is not None:
            q = q.limit(self.row_limit)
        if self.row_offset is not None:
            q = q.offset(self.row_offset)
        return q

    def _build_set_op(self, params: list[Any], dialect: Dialect) -> str:
        left_sql = self.union_left.as_pypika(params, dialect).get_sql(quote_char='"')
        right_sql = self.union_right.as_pypika(params, dialect).get_sql(quote_char='"')
        sql = f"({left_sql}) {self.set_op} ({right_sql})"
        if self.orderings:
            parts: list[str] = []
            for f, is_desc in self.orderings:
                direction = "DESC" if is_desc else "ASC"
                parts.append(f'"{f.column_name}" {direction}')
            sql += " ORDER BY " + ", ".join(parts)
        if self.row_limit is not None:
            sql += f" LIMIT {self.row_limit}"
        if self.row_offset is not None:
            sql += f" OFFSET {self.row_offset}"
        return sql

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        if self.ctes:
            return self._build_with(dialect)
        params: list[Any] = []
        if self.as_json is not None and self.alias is not None and self.inner is not None:
            # .aliased("x").json(): wrap inner query in json_build_object(alias, json_agg(...))
            inner = self.inner
            if getattr(inner, "__union_left__", None) is not None:
                inner_sql = inner._build_set_op(params, dialect)
            else:
                inner_sql = inner.as_pypika(params, dialect).get_sql(quote_char='"')
            cast_to = "::text" if self.as_json is JsonMode.RAW else ""
            sql = (
                f"SELECT json_build_object('{self.alias}',COALESCE(json_agg(t),'[]'::json))"
                f"{cast_to} FROM ({inner_sql}) t"
            )
            return sql, tuple(params)
        if self.union_left is not None:
            sql = self._build_set_op(params, dialect)
        else:
            sql = self.as_pypika(params, dialect).get_sql(quote_char='"')
        if self.as_json is not None:
            cast_to = "::text" if self.as_json is JsonMode.RAW else ""
            sql = f"SELECT row_to_json(t){cast_to} FROM ({sql}) t"
        return sql, tuple(params)

    def _build_with(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        cte_names = frozenset(v.__alias__ for v in self.ctes)
        cte_parts: list[str] = []
        for view in self.ctes:
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
        main_sql = self.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
        prefix = "WITH RECURSIVE " if self.recursive else "WITH "
        return prefix + ", ".join(cte_parts) + " " + main_sql, tuple(params)


class Selectable(Entity):
    """Mixin that adds SELECT and query-building capability. Inherit via Table or View.

    Each method here only *starts* a query -- it hands the entity to a
    :class:`Query` and lets that carry the chain from there.
    """

    @classmethod
    def _query(cls) -> Query:
        # `aliased()` hands back a class carrying __alias__/__inner__, and the
        # builder may be picked up again from there -- `.aliased("x").json()` is
        # one query, not two -- so a query started on one keeps them.
        return Query(entity=cls, alias=cls.__alias__, inner=cls.__inner__)

    @classmethod
    def select(cls, *proxies: Field[Any]) -> Query:
        return cls._query().select(*proxies)

    @classmethod
    def select_all(cls) -> Query:
        return cls._query().select_all()

    @classmethod
    def where(cls, filter: AnyFilter) -> Query:
        return cls._query().where(filter)

    @classmethod
    def order_by(cls, *fields: Field[Any], desc: bool = False) -> Query:
        return cls._query().order_by(*fields, desc=desc)

    @classmethod
    def limit(cls, n: int) -> Query:
        return cls._query().limit(n)

    @classmethod
    def offset(cls, n: int) -> Query:
        return cls._query().offset(n)

    @classmethod
    def distinct(cls) -> Query:
        return cls._query().distinct()

    @classmethod
    def join(cls, other: Any, *, on: AnyFilter) -> Query:
        return cls._query().join(other, on=on)

    @classmethod
    def left_join(cls, other: Any, *, on: AnyFilter) -> Query:
        return cls._query().left_join(other, on=on)

    @classmethod
    def right_join(cls, other: Any, *, on: AnyFilter) -> Query:
        return cls._query().right_join(other, on=on)

    @classmethod
    def cross_join(cls, other: Any) -> Query:
        return cls._query().cross_join(other)

    @classmethod
    def group_by(cls, *proxies: Field[Any]) -> Query:
        return cls._query().group_by(*proxies)

    @classmethod
    def having(cls, criterion: AnyFilter) -> Query:
        return cls._query().having(criterion)

    @classmethod
    def union(cls, other: Any, *, all: bool = False) -> Query:
        return cls._query().union(other, all=all)

    @classmethod
    def intersect(cls, other: Any) -> Query:
        return cls._query().intersect(other)

    @classmethod
    def exclude(cls, other: Any) -> Query:
        return cls._query().exclude(other)

    @classmethod
    def prefetch(cls, *children: Any) -> Query:
        return cls._query().prefetch(*children)

    @classmethod
    def json(cls, *, raw: bool = False) -> Query:
        return cls._query().json(raw=raw)

    @classmethod
    def as_scalar(cls) -> Any:
        return cls._query().as_scalar()

    @classmethod
    def as_pypika(cls, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        return cls._query().as_pypika(params, dialect, cte_names)

    @classmethod
    def build(cls, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        return cls._query().build(dialect)


class Writable(Entity):
    """Mixin that adds INSERT/UPDATE/DELETE capability. Inherit via Table, not directly."""

    @classmethod
    def insert(cls, rows: "list[dict[str, Any]] | None" = None, **kwargs: Any) -> InsertQuery:
        from .query import InsertQuery
        # Removed keyword args fall into **kwargs and would become bogus columns;
        # reject the old parameter explicitly so stale callers fail loudly.
        if "exclude_defaults" in kwargs:
            raise TypeError(
                "exclude_defaults was removed; insert() now sends exactly the columns you pass"
            )
        if rows is not None:
            if not rows:
                raise ValueError("insert requires at least one row")
            first_cols = set(rows[0].keys())
            if any(set(r.keys()) != first_cols for r in rows[1:]):
                raise ValueError("all rows must have a consistent set of columns")
            return InsertQuery(source=cls.__table__, rows=tuple(dict(r) for r in rows), is_many=True)
        return InsertQuery(source=cls.__table__, rows=(kwargs,), is_many=False)

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

    # Populated by ``D2Meta.__new__`` when ``query=`` is supplied.
    __view_query__: ClassVar[Any] = None
