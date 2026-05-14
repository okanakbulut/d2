
import re
import typing
from typing import Any, ClassVar, Generic, TYPE_CHECKING, TypeVar, cast, overload

import pypika
import pypika.terms
from pypika.utils import format_alias_sql, format_quotes

from .model import FieldDef, TableMeta

if TYPE_CHECKING:
    from .filter import Filter
    from .query import InsertQuery, QueryBuilder


class _NamespacedField(pypika.terms.Field):
    """pypika Field that always renders as [schema.]table.column."""

    def get_sql(self, **kwargs: Any) -> str:
        with_alias = kwargs.pop("with_alias", False)
        kwargs.pop("with_namespace", None)
        quote_char = kwargs.pop("quote_char", None)

        field_sql = format_quotes(self.name, quote_char)

        if self.table:
            tbl = cast(pypika.Table, self.table)
            table_sql = format_quotes(tbl.get_table_name(), quote_char)
            field_sql = f"{table_sql}.{field_sql}"

        field_alias = getattr(self, "alias", None)
        if with_alias:
            return format_alias_sql(field_sql, field_alias, quote_char=quote_char, **kwargs)
        return field_sql

T = TypeVar("T")


class Field(Generic[T]):
    column_name: str
    python_type: type
    field_def: FieldDef
    pika_field: pypika.Field

    def __init__(
        self,
        column_name: str,
        python_type: type,
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
        proxy = field_cls(col_name, python_type, fd, _NamespacedField(col_name, table=pika_table))
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


class Selectable(metaclass=NormMeta):
    __table__: ClassVar[pypika.Table]
    __fields__: ClassVar[tuple[Field[Any], ...]]

    @classmethod
    def select(cls, *proxies: "Field[Any]") -> "QueryBuilder":
        from .query import QueryBuilder
        return QueryBuilder(source=cls.__table__, columns=proxies)

    @classmethod
    def select_all(cls) -> "QueryBuilder":
        from .query import QueryBuilder
        return QueryBuilder(source=cls.__table__, columns=cls.__fields__)


class Table(Selectable):
    """Writable database table."""

    @classmethod
    def insert(cls, data: "dict[str, Any] | list[dict[str, Any]]") -> "InsertQuery":
        from .query import InsertQuery
        rows = (data,) if isinstance(data, dict) else tuple(data)
        return InsertQuery(source=cls.__table__, rows=rows)


class View(Selectable):
    """Read-only table or subquery."""
