"""In-memory schema state for migration replay/diff.

Only `tables` is exercised in the tracer slice (issue 140); other fields are
present but empty for forward compatibility.
"""


from dataclasses import dataclass, field
from typing import Any


# Backward-compat aliases: existing migration files on disk pass raw dicts to
# AddConstraint; keep these so those files continue to import-and-run.
ConstraintDict = dict[str, Any]
IndexDict = dict[str, Any]


@dataclass
class UniqueConstraint:
    name: str
    columns: tuple[str, ...]
    type: str = field(default="unique", init=False)


@dataclass
class ForeignKeyConstraint:
    name: str
    columns: tuple[str, ...]
    references_schema: str | None
    references_table: str
    references_column: str
    on_delete: str | None = None
    on_update: str | None = None
    type: str = field(default="foreign_key", init=False)


@dataclass
class IndexDef:
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    method: str | None = None
    where: str | None = None  # partial-index predicate (SQL, no leading WHERE)


Constraint = UniqueConstraint | ForeignKeyConstraint

# SERIAL macro → underlying integer type. Per ADR-0004, state stores the
# integer type and a `has_sequence_default` flag; DDL still emits the macro.
_SERIAL_TO_INT: dict[str, str] = {
    "SERIAL": "INTEGER",
    "BIGSERIAL": "BIGINT",
    "SMALLSERIAL": "SMALLINT",
}
_INT_TO_SERIAL: dict[str, str] = {v: k for k, v in _SERIAL_TO_INT.items()}


def serial_display_type(int_type: str, has_sequence_default: bool) -> str:
    """Return the SERIAL macro for a column with a sequence default, or the raw type."""
    if has_sequence_default and int_type in _INT_TO_SERIAL:
        return _INT_TO_SERIAL[int_type]
    return int_type


class SchemaError(Exception):
    """Raised when an operation cannot be applied to the current SchemaState."""


@dataclass
class ColumnState:
    type: str                # SQL type — normalized (never SERIAL/BIGSERIAL/SMALLSERIAL)
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False
    has_sequence_default: bool = False

    def __post_init__(self) -> None:
        upper = self.type.upper()
        if upper in _SERIAL_TO_INT:
            self.type = _SERIAL_TO_INT[upper]
            self.has_sequence_default = True

    def to_ddl(self, name: str) -> str:
        display_type = _INT_TO_SERIAL[self.type] if self.has_sequence_default and self.type in _INT_TO_SERIAL else self.type
        parts = [f'"{name}"', display_type]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        if self.primary_key:
            parts.append("PRIMARY KEY")
        return " ".join(parts)


def _empty_constraints() -> list[Constraint]:
    return []


def _empty_indexes() -> list[IndexDef]:
    return []


@dataclass
class TableState:
    columns: dict[str, ColumnState]
    constraints: list[Constraint] = field(default_factory=_empty_constraints)
    indexes: list[IndexDef] = field(default_factory=_empty_indexes)
    schema: str | None = None


@dataclass
class ViewState:
    definition: str
    columns: tuple[tuple[str, type[Any]], ...]
    schema: str | None = None


@dataclass
class SchemaState:
    tables: dict[str, TableState] = field(default_factory=dict[str, TableState])
    views: dict[str, ViewState] = field(default_factory=dict[str, ViewState])
    extensions: set[str] = field(default_factory=set[str])
    schemas: set[str] = field(default_factory=set[str])
