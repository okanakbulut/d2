"""Snapshot: project Table subclasses into a SchemaState.

Mirrors the normalization done by migration replay so that `diff_states(current,
target)` is stable when nothing changed.
"""


from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, cast, get_origin
from uuid import UUID

import pypika

from .naming import auto_fk_name, auto_index_name, auto_unique_name
from .operations import CreateTable
from .state import (
    ColumnState,
    ForeignKeyConstraint,
    IndexDef,
    SchemaState,
    UniqueConstraint,
    ViewState,
)


# ---------------------------------------------------------------------------
# Protocols — make the shapes snapshot.py reads from norm.schema explicit.
# These are static-only (not runtime_checkable) so there's zero runtime cost.
# ---------------------------------------------------------------------------

class _FKDef(Protocol):
    to: Any
    columns: tuple[str, ...] | None
    name: str | None
    on_delete: str | None
    on_update: str | None


class _FieldDef(Protocol):
    primary_key: bool
    db_default: bool
    nullable: bool
    unique: bool
    index: bool
    fk: _FKDef | None


class _FieldProxy(Protocol):
    column_name: str
    python_type: type[Any]
    field_def: _FieldDef


class _IndexDef(Protocol):
    columns: tuple[str, ...]
    name: str | None
    unique: bool
    method: str | None


class _TableMeta(Protocol):
    extensions: tuple[str, ...]
    schema: str | None
    foreign_keys: tuple[_FKDef, ...]
    indexes: tuple[_IndexDef, ...]


class _NormTable(Protocol):
    __fields__: tuple[_FieldProxy, ...]
    __table__: pypika.Table


# ---------------------------------------------------------------------------
# Python type → SQL type map
# ---------------------------------------------------------------------------

# Python type → SQL type. `int` maps to BIGINT by default; the BIGSERIAL upgrade
# for `primary_key + db_default` happens in `column_spec_for_field`.
PY_TO_SQL: dict[type, str] = {
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


def sql_type_for(python_type: Any) -> str:
    # Generic aliases like `dict[str, Any]` aren't hashable into our type-keyed
    # table directly; strip to the origin (`dict`) for lookup.
    lookup = get_origin(python_type) or python_type
    if lookup in PY_TO_SQL:
        return PY_TO_SQL[lookup]
    raise TypeError(f"no SQL mapping for Python type {python_type!r}")


def column_spec_for_field(field: _FieldProxy) -> ColumnState:
    fd: _FieldDef = field.field_def
    if fd.primary_key and fd.db_default and field.python_type is int:
        # ColumnState.__post_init__ normalizes BIGSERIAL → BIGINT + has_sequence_default=True
        return ColumnState(type="BIGSERIAL", nullable=False, primary_key=True)
    sql_type = sql_type_for(field.python_type)
    return ColumnState(
        type=sql_type,
        nullable=fd.nullable,
        primary_key=fd.primary_key,
    )


def resolve_fk_target(target: Any) -> tuple[str | None, str, str]:
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


def fk_constraint(
    *,
    table: str,
    fk: _FKDef,
    columns: tuple[str, ...] | None = None,
) -> ForeignKeyConstraint:
    ref_schema, ref_table, ref_column = resolve_fk_target(fk.to)
    cols: tuple[str, ...] | None = columns if columns is not None else fk.columns
    if cols is None:
        raise ValueError(
            "ForeignKey declared on TableMeta must specify columns=(...,)"
        )
    name = fk.name or auto_fk_name(table, cols)
    return ForeignKeyConstraint(
        name=name,
        columns=tuple(cols),
        references_schema=ref_schema,
        references_table=ref_table,
        references_column=ref_column,
        on_delete=fk.on_delete,
        on_update=fk.on_update,
    )


def inline_view_params(sql: str, params: tuple[Any, ...]) -> str:
    """Inline `$N` placeholders for use inside a VIEW definition (which cannot
    bind runtime parameters). Supports None, bool, int/float, and str. Other
    types raise — by design: a view definition that needs richer literals
    should be authored with explicit SQL fragments.
    """
    result = sql
    for i in range(len(params), 0, -1):  # replace longest indices first
        placeholder = f"${i}"
        result = result.replace(placeholder, sql_literal(params[i - 1]))
    return result


_SUPPORTED_SQL_LITERAL_TYPES = (type(None), bool, int, float, str)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    supported = ", ".join(t.__name__ for t in _SUPPORTED_SQL_LITERAL_TYPES)
    raise TypeError(
        f"cannot inline value of type {type(value).__name__!r} into a view definition; "
        f"supported types are: {supported}"
    )


def snapshot_view(cls: type, state: SchemaState) -> None:
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
    definition = inline_view_params(raw_sql, params)
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

    state = SchemaState()
    for cls in models:
        if issubclass(cls, View) and not issubclass(cls, Table):
            snapshot_view(cls, state)
            continue
        if not issubclass(cls, Table):
            continue

        norm_table = cast(_NormTable, cls)
        columns: dict[str, ColumnState] = {}
        for f in norm_table.__fields__:
            columns[f.column_name] = column_spec_for_field(f)
        pika_table: pypika.Table = norm_table.__table__
        table_name: str = pika_table.get_table_name()
        schema_obj: Any = getattr(pika_table, "_schema", None)
        schema_str: str | None = (
            cast(str, schema_obj.get_sql(quote_char='"')) if schema_obj else None
        )
        if schema_str:
            schema_str = schema_str.strip('"')
        CreateTable(table=table_name, columns=columns, schema=schema_str).apply(state)

        table_state = state.tables[table_name]
        for f in norm_table.__fields__:
            fd: _FieldDef = f.field_def
            col = f.column_name
            if fd.unique:
                table_state.constraints.append(
                    UniqueConstraint(
                        name=auto_unique_name(table_name, (col,)),
                        columns=(col,),
                    )
                )
            if fd.index:
                table_state.indexes.append(
                    IndexDef(
                        name=auto_index_name(table_name, (col,)),
                        columns=(col,),
                        unique=False,
                        method=None,
                    )
                )
            if fd.fk is not None:
                table_state.constraints.append(
                    fk_constraint(table=table_name, fk=fd.fk, columns=(col,))
                )

        raw_meta: Any = getattr(cls, "__meta__", None)
        if raw_meta is not None:
            meta = cast(_TableMeta, raw_meta)
            for ext in meta.extensions or ():
                state.extensions.add(ext)
            meta_schema: str | None = meta.schema
            if meta_schema is not None and meta_schema != "public":
                state.schemas.add(meta_schema)
            for fk in meta.foreign_keys or ():
                table_state.constraints.append(
                    fk_constraint(table=table_name, fk=fk)
                )
            for idx in meta.indexes or ():
                cols: tuple[str, ...] = tuple(idx.columns)
                idx_name: str = idx.name or (
                    auto_unique_name(table_name, cols)
                    if idx.unique
                    else auto_index_name(table_name, cols)
                )
                table_state.indexes.append(
                    IndexDef(
                        name=idx_name,
                        columns=cols,
                        unique=idx.unique,
                        method=idx.method,
                    )
                )
    return state
