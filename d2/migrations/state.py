"""In-memory schema state for migration replay/diff.

Only `tables` is exercised in the tracer slice (issue 140); other fields are
present but empty for forward compatibility.
"""


from typing import Any, ClassVar

import msgspec


# Backward-compat aliases: existing migration files on disk pass raw dicts to
# AddConstraint; keep these so those files continue to import-and-run.
ConstraintDict = dict[str, Any]
IndexDict = dict[str, Any]


class _TaggedConstraint(msgspec.Struct):
    """Constraint variant carrying a `type` tag.

    The tag is a ClassVar rather than a field, so it cannot be passed to the
    constructor -- a UniqueConstraint can never claim to be a foreign key, which
    matters because `constraint_from_dict` rebuilds these from the tag alone.
    ClassVars are absent from msgspec's generated repr, so it is restored here;
    the field list comes from the struct itself and cannot drift.
    """

    type: ClassVar[str]

    def __repr__(self) -> str:
        args = ", ".join(
            f"{f.name}={getattr(self, f.name)!r}" for f in msgspec.structs.fields(self)
        )
        return f"{type(self).__name__}({args}, type={self.type!r})"


class UniqueConstraint(_TaggedConstraint):
    name: str
    columns: tuple[str, ...]
    type: ClassVar[str] = "unique"


class ForeignKeyConstraint(_TaggedConstraint):
    name: str
    columns: tuple[str, ...]
    references_schema: str | None
    references_table: str
    references_column: str
    on_delete: str | None = None
    on_update: str | None = None
    type: ClassVar[str] = "foreign_key"


class IndexDef(msgspec.Struct):
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


class ColumnState(msgspec.Struct):
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


class TableState(msgspec.Struct):
    columns: dict[str, ColumnState]
    constraints: list[Constraint] = []
    indexes: list[IndexDef] = []
    schema: str | None = None


class ViewState(msgspec.Struct):
    definition: str
    columns: tuple[tuple[str, type[Any]], ...]
    schema: str | None = None


class SchemaState(msgspec.Struct):
    tables: dict[str, TableState] = {}
    views: dict[str, ViewState] = {}
    extensions: set[str] = set()
    schemas: set[str] = set()
