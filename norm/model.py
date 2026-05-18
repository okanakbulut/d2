
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ForeignKey:
    """A foreign-key constraint declaration.

    `to` accepts either a `Field` proxy (refactor-safe, type-checked) or a
    `"schema.table.column"` / `"table.column"` string (for forward refs or
    tables outside norm).
    """

    to: Any
    on_delete: str | None = None
    on_update: str | None = None
    name: str | None = None
    columns: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FieldDef:
    primary_key: bool = False
    db_default: bool = False
    index: bool = False
    unique: bool = False
    name: str | None = None
    nullable: bool = False
    fk: ForeignKey | None = None


def field(
    *,
    db_default: bool = False,
    name: str | None = None,
    unique: bool = False,
    index: bool = False,
    fk: ForeignKey | None = None,
) -> Any:
    return FieldDef(
        db_default=db_default, name=name, unique=unique, index=index, fk=fk,
    )


@dataclass(frozen=True)
class IndexDef:
    columns: tuple[str, ...]
    name: str | None = None
    unique: bool = False
    method: str | None = None


@dataclass(frozen=True)
class TableMeta:
    table: str | None = None
    schema: str | None = None
    indexes: tuple[IndexDef, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
