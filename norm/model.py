
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldDef:
    primary_key: bool = False
    db_default: bool = False
    index: bool = False
    unique: bool = False
    name: str | None = None
    nullable: bool = False


def field(
    *,
    db_default: bool = False,
    name: str | None = None,
    unique: bool = False,
    index: bool = False,
) -> Any:
    return FieldDef(db_default=db_default, name=name, unique=unique, index=index)


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
