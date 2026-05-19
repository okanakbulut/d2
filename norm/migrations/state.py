"""In-memory schema state for migration replay/diff.

Only `tables` is exercised in the tracer slice (issue 140); other fields are
present but empty for forward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ConstraintDict = dict[str, Any]
IndexDict = dict[str, Any]


class SchemaError(Exception):
    """Raised when an operation cannot be applied to the current SchemaState."""


@dataclass
class ColumnState:
    type: str                # SQL type — normalized (never SERIAL/BIGSERIAL/SMALLSERIAL)
    nullable: bool
    default: str | None = None
    primary_key: bool = False
    has_sequence_default: bool = False


@dataclass
class TableState:
    columns: dict[str, ColumnState]
    constraints: list[ConstraintDict] = field(default_factory=list[ConstraintDict])
    indexes: list[IndexDict] = field(default_factory=list[IndexDict])
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
