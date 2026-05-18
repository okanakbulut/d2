"""Snapshot: project Table subclasses into a SchemaState.

Mirrors the normalization done by migration replay so that `diff_states(current,
target)` is stable when nothing changed.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .operations import ColumnDef, CreateTable
from .state import SchemaState


# Python type → SQL type. `int` maps to BIGINT by default; the BIGSERIAL upgrade
# for `primary_key + db_default` happens in `_column_def_for_field`.
_PY_TO_SQL: dict[type, str] = {
    int: "BIGINT",
    str: "TEXT",
    float: "DOUBLE PRECISION",
    bool: "BOOLEAN",
    datetime: "TIMESTAMPTZ",
    date: "DATE",
    Decimal: "NUMERIC",
    UUID: "UUID",
    dict: "JSONB",
    list: "JSONB",
    bytes: "BYTEA",
}


def _sql_type_for(python_type: type) -> str:
    if python_type in _PY_TO_SQL:
        return _PY_TO_SQL[python_type]
    raise TypeError(f"no SQL mapping for Python type {python_type!r}")


def _column_def_for_field(field: Any) -> ColumnDef:
    fd = field.field_def
    if fd.primary_key and fd.db_default and field.python_type is int:
        return ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True)
    sql_type = _sql_type_for(field.python_type)
    return ColumnDef(
        type=sql_type,
        nullable=fd.nullable,
        primary_key=fd.primary_key,
    )


def models_to_schema_state(models: list[type]) -> SchemaState:
    """Project the given model classes into a `SchemaState`.

    Only `Table` subclasses contribute table state. `View` subclasses are
    skipped here (handled by a later slice). Schema-level state (extensions,
    schemas) is empty.
    """
    from norm.schema import Table  # local import to avoid cycles

    state = SchemaState()
    for cls in models:
        if not (isinstance(cls, type) and issubclass(cls, Table)):
            continue
        columns: dict[str, ColumnDef] = {}
        for f in cls.__fields__:
            columns[f.column_name] = _column_def_for_field(f)
        table_name = cls.__table__.get_table_name()
        schema_name = getattr(cls.__table__, "_schema", None)
        schema_str = schema_name.get_sql(quote_char='"') if schema_name else None
        if schema_str:
            schema_str = schema_str.strip('"')
        CreateTable(table=table_name, columns=columns, schema=schema_str).apply(state)
    return state
