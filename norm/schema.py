
import re
import typing
from typing import Any, ClassVar, Generic, TYPE_CHECKING, TypeVar, cast, overload

import pypika
import pypika.functions
import pypika.terms
from pypika.utils import format_alias_sql, format_quotes

from .model import FieldDef, TableMeta

if TYPE_CHECKING:
    from .filter import Filter
    from .query import InsertQuery, QueryBuilder, UpdateQuery, DeleteQuery


class NamespacedField(pypika.terms.Field):
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
_EntityT = TypeVar("_EntityT", bound="Entity")


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

    def __eq__(self, other: Any) -> "Filter":  # type: ignore[override]
        from .filter import Filter
        if isinstance(other, Field):
            return Filter(field=self, value=other, op="col_eq")
        return Filter(field=self, value=other)

    def __ne__(self, other: Any) -> "Filter":  # type: ignore[override]
        from .filter import Filter
        return Filter(field=self, value=other, op="ne")

    def __lt__(self, other: Any) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=other, op="lt")

    def __le__(self, other: Any) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=other, op="lte")

    def __gt__(self, other: Any) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=other, op="gt")

    def __ge__(self, other: Any) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=other, op="gte")

    def like(self, pattern: str) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=pattern, op="like")

    def ilike(self, pattern: str) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=pattern, op="ilike")

    def isin(self, values: list[Any]) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=tuple(values), op="in")

    def notin(self, values: list[Any]) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=tuple(values), op="notin")

    def isnull(self) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=None, op="null")

    def isnotnull(self) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=None, op="notnull")

    def between(self, lo: Any, hi: Any) -> "Filter":
        from .filter import Filter
        return Filter(field=self, value=(lo, hi), op="between")

    def as_(self, alias: str) -> "Field[T]":
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

    def __add__(self, other: Any) -> "Field[Any]":
        return _arith_field(self, "+", other)

    def __sub__(self, other: Any) -> "Field[Any]":
        return _arith_field(self, "-", other)

    def __mul__(self, other: Any) -> "Field[Any]":
        return _arith_field(self, "*", other)

    def __truediv__(self, other: Any) -> "Field[Any]":
        return _arith_field(self, "/", other)

    def __hash__(self) -> int:
        return hash(self.column_name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.column_name!r})"

    def __setattr__(self, name: str, value: Any) -> None:  # type: ignore[override]
        raise AttributeError(f"cannot set '{name}' on {type(self).__name__}")


class _ArithField(Field[Any]):
    def __init__(self, left: "Field[Any]", op: str, right: Any) -> None:
        object.__setattr__(self, "column_name", left.column_name)
        object.__setattr__(self, "python_type", left.python_type)
        object.__setattr__(self, "field_def", left.field_def)
        object.__setattr__(self, "pika_field", left.pika_field)
        object.__setattr__(self, "_left", left)
        object.__setattr__(self, "_op", op)
        object.__setattr__(self, "_right", right)

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        left_term = self._left.to_column(params, dialect)  # type: ignore[attr-defined]
        right = self._right  # type: ignore[attr-defined]
        op = self._op  # type: ignore[attr-defined]
        if isinstance(right, Field):
            right_term = right.pika_field
        else:
            params.append(right)
            right_term = pypika.terms.Parameter(dialect.placeholder(len(params)))
        ops: dict[str, Any] = {"+": left_term + right_term, "-": left_term - right_term,
                               "*": left_term * right_term, "/": left_term / right_term}
        return ops[op]


def _arith_field(left: "Field[Any]", op: str, right: Any) -> "_ArithField":
    return _ArithField(left, op, right)


class _AggField(Field[T]):
    """A Field backed by a pypika aggregate (or scalar) term."""

    def __init__(self, python_type: type[T], pika_term: pypika.terms.Term) -> None:
        object.__setattr__(self, "column_name", "")
        object.__setattr__(self, "python_type", python_type)
        object.__setattr__(self, "field_def", FieldDef())
        object.__setattr__(self, "pika_field", pika_term)

    def to_column(self, params: list[Any], dialect: Any) -> Any:
        return self.pika_field

    def as_(self, alias: str) -> "Field[T]":
        return _AggField(self.python_type, self.pika_field.as_(alias))


class _CoalesceField(Field[T]):
    """COALESCE(col, default) — default is bound as a parameter at build time."""

    _source: "Field[T]"
    _default: Any

    def __init__(self, source: "Field[T]", default: Any) -> None:
        object.__setattr__(self, "column_name", source.column_name)
        object.__setattr__(self, "python_type", source.python_type)
        object.__setattr__(self, "field_def", source.field_def)
        object.__setattr__(self, "pika_field", source.pika_field)
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_default", default)

    def as_(self, alias: str) -> "Field[T]":
        source: Field[T] = object.__getattribute__(self, "_source")
        default: Any = object.__getattribute__(self, "_default")
        new = _CoalesceField(source, default)
        object.__setattr__(new, "_alias", alias)
        return new

    def to_column(self, params: list[Any], dialect: Any) -> Any:  # type: ignore[override]
        params.append(self._default)  # type: ignore[attr-defined]
        default_term = pypika.terms.Parameter(dialect.placeholder(len(params)))
        term = pypika.functions.Coalesce(self._source.pika_field, default_term)  # type: ignore[attr-defined]
        alias = getattr(self, "_alias", None)
        if alias:
            return term.as_(alias)
        return term


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
        if origin is not None and isinstance(origin, type) and issubclass(origin, Field):
            args = typing.get_args(hint)
            python_type: type = args[0] if args else type(None)
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

        class_default = vars(model).get(attr_name)
        if isinstance(class_default, FieldDef):
            db_default = class_default.db_default
            col_name_override = class_default.name

        fd = FieldDef(
            primary_key=primary_key,
            unique=unique,
            index=index,
            db_default=db_default,
            name=col_name_override,
        )
        result.append((attr_name, python_type, fd, field_cls))

    return result


def _setup_table(cls: type) -> None:
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

    cls.__table__ = pika_table  # type: ignore[attr-defined]
    cls.__fields__ = tuple(field_proxies)  # type: ignore[attr-defined]


class NormMeta(type):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "NormMeta":
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if any(isinstance(b, NormMeta) for b in bases):
            _setup_table(cls)
        return cls


class Entity(metaclass=NormMeta):
    """Base for all norm-managed database objects. Do not use directly — subclass Table or View."""

    __table__: ClassVar[pypika.Table]
    __fields__: ClassVar[tuple[Field[Any], ...]]

    @classmethod
    def aliased(cls: "type[_EntityT]", alias: str) -> "type[_EntityT]":
        orig_table: pypika.Table = cls.__table__
        real_name: str = orig_table._table_name  # type: ignore[attr-defined]
        schema_obj = orig_table._schema  # type: ignore[attr-defined]

        pika_table = pypika.Table(real_name, schema=schema_obj).as_(alias)  # type: ignore[reportUnknownArgumentType, reportArgumentType]

        field_overrides: dict[str, Any] = {}
        new_fields: list[Field[Any]] = []
        for attr_name, value in vars(cls).items():
            if isinstance(value, Field):
                new_pika = NamespacedField(value.column_name, table=pika_table)
                new_proxy: Field[Any] = type(value)(value.column_name, value.python_type, value.field_def, new_pika)  # type: ignore[reportUnknownMemberType]
                field_overrides[attr_name] = new_proxy
                new_fields.append(new_proxy)

        ns: dict[str, Any] = {
            "__table__": pika_table,
            "__fields__": tuple(new_fields),
            **field_overrides,
        }
        proxy = type.__new__(type, cls.__name__, (object,), ns)
        proxy.select = classmethod(  # type: ignore[attr-defined]
            lambda c, *proxies: __import__("norm.query", fromlist=["QueryBuilder"]).QueryBuilder(
                source=c.__table__, columns=proxies  # type: ignore[attr-defined]
            )
        )
        proxy.select_all = classmethod(  # type: ignore[attr-defined]
            lambda c: __import__("norm.query", fromlist=["QueryBuilder"]).QueryBuilder(
                source=c.__table__, columns=c.__fields__  # type: ignore[attr-defined]
            )
        )
        return proxy  # type: ignore[return-value]


class Selectable(Entity):
    """Mixin that adds SELECT capability. Inherit via Table or View, not directly."""

    @classmethod
    def select(cls, *proxies: "Field[Any]") -> "QueryBuilder":
        from .query import QueryBuilder
        return QueryBuilder(source=cls.__table__, columns=proxies)

    @classmethod
    def select_all(cls) -> "QueryBuilder":
        from .query import QueryBuilder
        return QueryBuilder(source=cls.__table__, columns=cls.__fields__)


class Writable(Entity):
    """Mixin that adds INSERT/UPDATE/DELETE capability. Inherit via Table, not directly."""

    @classmethod
    def _default_columns(cls) -> "frozenset[str]":
        return frozenset(
            f.column_name for f in cls.__fields__
            if f.field_def.db_default or f.field_def.primary_key
        )

    @classmethod
    def insert(cls, rows: "list[dict[str, Any]] | None" = None, *, exclude_defaults: bool = True, **kwargs: Any) -> "InsertQuery":
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
    def update(cls, **assignments: Any) -> "UpdateQuery":
        from .query import UpdateQuery
        col_assignments = tuple(
            (getattr(cls, attr).column_name, value)
            for attr, value in assignments.items()
        )
        return UpdateQuery(source=cls.__table__, assignments=col_assignments)

    @classmethod
    def delete(cls) -> "DeleteQuery":
        from .query import DeleteQuery
        return DeleteQuery(source=cls.__table__)


class Table(Selectable, Writable):
    """Readable and writable database table."""


class View(Selectable):
    """Read-only database view or table."""


