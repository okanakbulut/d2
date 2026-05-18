
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


def field(*, db_default: bool = False, name: str | None = None) -> Any:
    return FieldDef(db_default=db_default, name=name)


@dataclass(frozen=True)
class TableMeta:
    table: str | None = None
    schema: str | None = None
