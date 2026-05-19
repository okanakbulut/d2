"""Snapshot: project Table subclasses into a SchemaState.

Mirrors the normalization done by migration replay so that `diff_states(current,
target)` is stable when nothing changed.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast, get_origin
from uuid import UUID

import pypika

from .naming import auto_fk_name, auto_index_name, auto_unique_name
from .operations import ColumnDef, CreateTable
from .state import ConstraintDict, SchemaState, ViewState


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


def _sql_type_for(python_type: Any) -> str:
    # Generic aliases like `dict[str, Any]` aren't hashable into our type-keyed
    # table directly; strip to the origin (`dict`) for lookup.
    lookup = get_origin(python_type) or python_type
    if lookup in _PY_TO_SQL:
        return _PY_TO_SQL[lookup]
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
        pika_table = cast(pypika.Table, pika_field.table)
        ref_table: str = pika_table.get_table_name()
        schema_obj: Any = getattr(pika_table, "_schema", None)
        ref_schema: str | None = (
            cast(str, schema_obj.get_sql(quote_char='"')).strip('"')
            if schema_obj
            else None
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
) -> ConstraintDict:
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


def _inline_view_params(sql: str, params: tuple[Any, ...]) -> str:
    """Inline `$N` placeholders for use inside a VIEW definition (which cannot
    bind runtime parameters). Supports None, bool, int/float, and str. Other
    types raise — by design: a view definition that needs richer literals
    should be authored with explicit SQL fragments.
    """
    result = sql
    for i in range(len(params), 0, -1):  # replace longest indices first
        placeholder = f"${i}"
        result = result.replace(placeholder, _sql_literal(params[i - 1]))
    return result


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    raise TypeError(
        f"cannot inline value of type {type(value).__name__!r} into a view definition"
    )


def _snapshot_view(cls: type, state: SchemaState) -> None:
    query: Any = getattr(cls, "__view_query__", None)
    if query is None:
        return
    pika_table = cast(pypika.Table, getattr(cls, "__table__"))
    view_name: str = pika_table.get_table_name()
    schema_obj: Any = getattr(pika_table, "_schema", None)
    schema_str: str | None = (
        cast(str, schema_obj.get_sql(quote_char='"')).strip('"')
        if schema_obj
        else None
    )
    raw_sql, params = cast(tuple[str, tuple[Any, ...]], query.build())
    definition = _inline_view_params(raw_sql, params)
    columns: tuple[tuple[str, type[Any]], ...] = tuple(
        (
            cast(str, getattr(c.pika_field, "alias", None) or c.column_name),
            cast("type[Any]", c.python_type),
        )
        for c in cast(tuple[Any, ...], query.__columns__)
    )
    state.views[view_name] = ViewState(
        definition=definition,
        columns=columns,
        schema=schema_str,
    )


def models_to_schema_state(models: list[type]) -> SchemaState:
    """Project the given model classes into a `SchemaState`.

    `Table` subclasses contribute table state; `View` subclasses contribute
    view state via their `__view_query__`. Schema-level state (extensions,
    schemas) is empty.
    """
    from norm.schema import Table, View  # local import to avoid cycles
    from .state import IndexDict

    state = SchemaState()
    for cls in models:
        if issubclass(cls, View) and not issubclass(cls, Table):
            _snapshot_view(cls, state)
            continue
        if not issubclass(cls, Table):
            continue
        columns: dict[str, ColumnDef] = {}
        for f in cls.__fields__:
            columns[f.column_name] = _column_def_for_field(f)
        pika_table = cls.__table__
        table_name: str = pika_table.get_table_name()
        schema_name: Any = getattr(pika_table, "_schema", None)
        schema_str: str | None = (
            cast(str, schema_name.get_sql(quote_char='"')) if schema_name else None
        )
        if schema_str:
            schema_str = schema_str.strip('"')
        CreateTable(table=table_name, columns=columns, schema=schema_str).apply(state)

        table_state = state.tables[table_name]
        for f in cls.__fields__:
            fd = f.field_def
            col = f.column_name
            if fd.unique:
                unique_constraint: ConstraintDict = {
                    "type": "unique",
                    "name": auto_unique_name(table_name, (col,)),
                    "columns": (col,),
                }
                table_state.constraints.append(unique_constraint)
            if fd.index:
                index_entry: IndexDict = {
                    "name": auto_index_name(table_name, (col,)),
                    "columns": (col,),
                    "unique": False,
                    "method": None,
                }
                table_state.indexes.append(index_entry)
            if fd.fk is not None:
                table_state.constraints.append(
                    _fk_constraint_dict(
                        table=table_name, fk=fd.fk, columns=(col,),
                    )
                )

        meta: Any = getattr(cls, "__meta__", None)
        if meta is not None:
            for ext in getattr(meta, "extensions", ()) or ():
                state.extensions.add(ext)
            meta_schema = getattr(meta, "schema", None)
            if meta_schema is not None and meta_schema != "public":
                state.schemas.add(meta_schema)
            for fk in getattr(meta, "foreign_keys", ()) or ():
                table_state.constraints.append(
                    _fk_constraint_dict(table=table_name, fk=fk)
                )
            for idx in getattr(meta, "indexes", ()) or ():
                cols: tuple[str, ...] = tuple(idx.columns)
                idx_name: str = idx.name or (
                    auto_unique_name(table_name, cols)
                    if idx.unique
                    else auto_index_name(table_name, cols)
                )
                meta_idx_entry: IndexDict = {
                    "name": idx_name,
                    "columns": cols,
                    "unique": idx.unique,
                    "method": idx.method,
                }
                table_state.indexes.append(meta_idx_entry)
    return state
