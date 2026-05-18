"""DDL operation dataclasses.

Tracer slice (issue 140) implements `CreateTable` + `ColumnDef` only.
Each op has `apply(state)` (mutates SchemaState) and `to_ddl()` (returns SQL).
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import ColumnState, SchemaState, TableState


# SERIAL macro → underlying integer type. Per ADR-0004, state stores the
# integer type and a `_has_sequence_default` flag; DDL still emits the macro.
_SERIAL_TO_INT: dict[str, str] = {
    "SERIAL": "INTEGER",
    "BIGSERIAL": "BIGINT",
    "SMALLSERIAL": "SMALLINT",
}


@dataclass
class ColumnDef:
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False

    def to_ddl(self, name: str) -> str:
        parts = [f'"{name}"', self.type]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        if self.primary_key:
            parts.append("PRIMARY KEY")
        return " ".join(parts)

    def to_column_state(self) -> ColumnState:
        upper = self.type.upper()
        if upper in _SERIAL_TO_INT:
            return ColumnState(
                type=_SERIAL_TO_INT[upper],
                nullable=self.nullable,
                default=self.default,
                primary_key=self.primary_key,
                _has_sequence_default=True,
            )
        return ColumnState(
            type=self.type,
            nullable=self.nullable,
            default=self.default,
            primary_key=self.primary_key,
            _has_sequence_default=False,
        )


@dataclass
class CreateTable:
    table: str
    columns: dict[str, ColumnDef]
    schema: str | None = None

    def _qualified(self) -> str:
        if self.schema:
            return f'"{self.schema}"."{self.table}"'
        return f'"{self.table}"'

    def to_ddl(self) -> str:
        col_ddls = [cd.to_ddl(name) for name, cd in self.columns.items()]
        return (
            f"CREATE TABLE IF NOT EXISTS {self._qualified()} "
            f"({', '.join(col_ddls)})"
        )

    def apply(self, state: SchemaState) -> None:
        cols = {name: cd.to_column_state() for name, cd in self.columns.items()}
        state.tables[self.table] = TableState(columns=cols, schema=self.schema)
