
from dataclasses import dataclass
from typing import Any

from .db import DbExpr, ReferentialAction

# Sentinel: "infer schema from module path" — the default when schema is not explicit.
# schema=None means "no schema prefix" (public); schema=_INFER means "derive from module".
_INFER: Any = object()


@dataclass(frozen=True)
class FieldDef:
    default: DbExpr | None = None
    index: bool = False
    unique: bool = False
    name: str | None = None
    nullable: bool = False
    references: type | None = None  # populated by _parse_fields for ForeignKey[Model]
    on_delete: ReferentialAction | None = None
    on_update: ReferentialAction | None = None


def field(
    *,
    default: DbExpr | None = None,
    on_delete: ReferentialAction | None = None,
    on_update: ReferentialAction | None = None,
    name: str | None = None,
    unique: bool = False,
    index: bool = False,
) -> Any:
    return FieldDef(
        default=default,
        on_delete=on_delete,
        on_update=on_update,
        name=name,
        unique=unique,
        index=index,
    )


@dataclass(frozen=True)
class IndexDef:
    columns: tuple[str, ...]
    name: str | None = None
    unique: bool = False
    method: str | None = None
    where: str | None = None  # partial-index predicate (SQL, no leading WHERE)


@dataclass(frozen=True)
class TableMeta:
    table: str | None = None
    schema: str | None = _INFER  # type: ignore[assignment]  — None = no prefix; default = infer from module
    indexes: tuple[IndexDef, ...] = ()
    extensions: tuple[str, ...] = ()
