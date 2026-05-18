"""Snapshot: project Table subclasses into a SchemaState.

Mirrors the normalization done by migration replay so that `diff_states(current,
target)` is stable when nothing changed.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .naming import auto_fk_name, auto_index_name, auto_unique_name
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


def _resolve_fk_target(target: Any) -> tuple[str | None, str, str]:
    """Resolve a `ForeignKey.to` value into (schema, table, column).

    Accepts either a `Field` proxy (uses its `pika_field.table`) or a string
    of the form `"schema.table.column"` or `"table.column"`.
    """
    from norm.schema import Field  # local import to avoid cycles

    if isinstance(target, Field):
        pika_field = target.pika_field
        pika_table = pika_field.table
        ref_table = pika_table.get_table_name()
        schema_obj = getattr(pika_table, "_schema", None)
        ref_schema = (
            schema_obj.get_sql(quote_char='"').strip('"') if schema_obj else None
        )
        return ref_schema, ref_table, target.column_name

    if isinstance(target, str):
        parts = target.split(".")
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 2:
            return None, parts[0], parts[1]
        raise ValueError(
            f"foreign-key string target must be 'schema.table.column' or "
            f"'table.column'; got {target!r}"
        )

    raise TypeError(
        f"ForeignKey.to must be a Field proxy or string; got {type(target).__name__}"
    )


def _fk_constraint_dict(
    *,
    table: str,
    fk: Any,
    columns: tuple[str, ...] | None = None,
) -> dict:
    ref_schema, ref_table, ref_column = _resolve_fk_target(fk.to)
    cols = columns if columns is not None else fk.columns
    if cols is None:
        raise ValueError(
            "ForeignKey declared on TableMeta must specify columns=(...,)"
        )
    name = fk.name or auto_fk_name(table, cols)
    return {
        "type": "foreign_key",
        "name": name,
        "columns": tuple(cols),
        "references_schema": ref_schema,
        "references_table": ref_table,
        "references_column": ref_column,
        "on_delete": fk.on_delete,
        "on_update": fk.on_update,
    }


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

        table_state = state.tables[table_name]
        for f in cls.__fields__:
            fd = f.field_def
            col = f.column_name
            if fd.unique:
                table_state.constraints.append(
                    {
                        "type": "unique",
                        "name": auto_unique_name(table_name, (col,)),
                        "columns": (col,),
                    }
                )
            if fd.index:
                table_state.indexes.append(
                    {
                        "name": auto_index_name(table_name, (col,)),
                        "columns": (col,),
                        "unique": False,
                        "method": None,
                    }
                )
            if fd.fk is not None:
                table_state.constraints.append(
                    _fk_constraint_dict(
                        table=table_name, fk=fd.fk, columns=(col,),
                    )
                )

        meta = getattr(cls, "__meta__", None)
        if meta is not None:
            for fk in getattr(meta, "foreign_keys", ()) or ():
                table_state.constraints.append(
                    _fk_constraint_dict(table=table_name, fk=fk)
                )
            for idx in getattr(meta, "indexes", ()) or ():
                cols = tuple(idx.columns)
                idx_name = idx.name or (
                    auto_unique_name(table_name, cols)
                    if idx.unique
                    else auto_index_name(table_name, cols)
                )
                table_state.indexes.append(
                    {
                        "name": idx_name,
                        "columns": cols,
                        "unique": idx.unique,
                        "method": idx.method,
                    }
                )
    return state
