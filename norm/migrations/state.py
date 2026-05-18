"""In-memory schema state for migration replay/diff.

Only `tables` is exercised in the tracer slice (issue 140); other fields are
present but empty for forward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class SchemaError(Exception):
    """Raised when an operation cannot be applied to the current SchemaState."""


@dataclass
class ColumnState:
    type: str                # SQL type — normalized (never SERIAL/BIGSERIAL/SMALLSERIAL)
    nullable: bool
    default: str | None = None
    primary_key: bool = False
    _has_sequence_default: bool = False


@dataclass
class TableState:
    columns: dict[str, ColumnState]
    constraints: list[dict] = field(default_factory=list)
    indexes: list[dict] = field(default_factory=list)
    schema: str | None = None


@dataclass
class SchemaState:
    tables: dict[str, TableState] = field(default_factory=dict)
    views: dict = field(default_factory=dict)
    extensions: set[str] = field(default_factory=set)
    schemas: set[str] = field(default_factory=set)
