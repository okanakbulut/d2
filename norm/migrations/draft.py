"""Diff two `SchemaState`s into a pair of forward/reverse operation lists.

Issues 141, 142: detect new/dropped tables and column add/drop + granular
modifications (type, nullability, default). Rename detection is NOT performed
(out of scope per ADR-0002 and the parent issue's resolved decisions);
renamed columns surface as drop + add and the user hand-edits the migration
file to use `RenameColumn`.
"""

from __future__ import annotations

from .operations import (
    AddColumn,
    AddConstraint,
    AlterColumnType,
    ColumnDef,
    CreateIndex,
    CreateTable,
    CreateView,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropConstraint,
    DropIndex,
    DropTable,
    DropView,
    SetColumnDefault,
    SetColumnNotNull,
)
from .state import ColumnState, SchemaState, TableState, ViewState


def _column_def_from_state(col: ColumnState) -> ColumnDef:
    return ColumnDef(
        type=col.type,
        nullable=col.nullable,
        default=col.default,
        primary_key=col.primary_key,
    )


def _create_table_from_state(name: str, table: TableState) -> CreateTable:
    cols = {n: _column_def_from_state(c) for n, c in table.columns.items()}
    return CreateTable(table=name, columns=cols, schema=table.schema)


def _diff_columns(
    table_name: str,
    schema: str | None,
    current_cols: dict[str, ColumnState],
    target_cols: dict[str, ColumnState],
) -> tuple[list, list]:
    """Return `(forward, reverse)` ops for column-level changes within a table."""
    forward: list = []
    reverse: list = []

    current_names = list(current_cols)
    target_names = list(target_cols)

    # Adds: columns in target but not in current, in target insertion order.
    for name in target_names:
        if name in current_cols:
            continue
        col = target_cols[name]
        forward.append(
            AddColumn(
                table=table_name,
                column=name,
                type=col.type,
                nullable=col.nullable,
                default=col.default,
                schema=schema,
            )
        )
        reverse.append(DropColumn(table=table_name, column=name, schema=schema))

    # Drops: columns in current but not in target, in current insertion order.
    for name in current_names:
        if name in target_cols:
            continue
        col = current_cols[name]
        forward.append(DropColumn(table=table_name, column=name, schema=schema))
        reverse.append(
            AddColumn(
                table=table_name,
                column=name,
                type=col.type,
                nullable=col.nullable,
                default=col.default,
                schema=schema,
            )
        )

    # Granular modifications for columns present in both, in target order.
    for name in target_names:
        if name not in current_cols:
            continue
        cur = current_cols[name]
        tgt = target_cols[name]

        if cur.type != tgt.type:
            forward.append(
                AlterColumnType(table=table_name, column=name, type=tgt.type, schema=schema)
            )
            reverse.append(
                AlterColumnType(table=table_name, column=name, type=cur.type, schema=schema)
            )

        if cur.nullable != tgt.nullable:
            if tgt.nullable:
                forward.append(
                    DropColumnNotNull(table=table_name, column=name, schema=schema)
                )
                reverse.append(
                    SetColumnNotNull(table=table_name, column=name, schema=schema)
                )
            else:
                forward.append(
                    SetColumnNotNull(table=table_name, column=name, schema=schema)
                )
                reverse.append(
                    DropColumnNotNull(table=table_name, column=name, schema=schema)
                )

        if cur.default != tgt.default:
            if tgt.default is None:
                forward.append(
                    DropColumnDefault(table=table_name, column=name, schema=schema)
                )
                reverse.append(
                    SetColumnDefault(
                        table=table_name, column=name, default=cur.default, schema=schema,
                    )
                )
            elif cur.default is None:
                forward.append(
                    SetColumnDefault(
                        table=table_name, column=name, default=tgt.default, schema=schema,
                    )
                )
                reverse.append(
                    DropColumnDefault(table=table_name, column=name, schema=schema)
                )
            else:
                forward.append(
                    SetColumnDefault(
                        table=table_name, column=name, default=tgt.default, schema=schema,
                    )
                )
                reverse.append(
                    SetColumnDefault(
                        table=table_name, column=name, default=cur.default, schema=schema,
                    )
                )

    return forward, reverse


def diff_states(
    current: SchemaState, target: SchemaState
) -> tuple[list, list]:
    """Return `(forward, reverse)` ops to go from `current` to `target`.

    `reverse` is the inverse sequence that undoes `forward` against
    `current`.
    """
    forward: list = []
    reverse: list = []

    current_tables = set(current.tables)
    target_tables = set(target.tables)

    # FK AddConstraint ops are deferred until after all CreateTable ops in the
    # forward list, so target tables exist when each FK is added.
    deferred_fk_adds: list = []

    for name in sorted(target_tables - current_tables):
        table = target.tables[name]
        forward.append(_create_table_from_state(name, table))
        reverse.append(DropTable(table=name, schema=table.schema))
        for c in table.constraints:
            add = AddConstraint(
                table=name, constraint=dict(c), schema=table.schema,
            )
            if c.get("type") == "foreign_key":
                deferred_fk_adds.append(add)
            else:
                forward.append(add)
        for idx in table.indexes:
            forward.append(_create_index_from_state(name, table.schema, idx))
        # DropTable in reverse removes everything; no separate cleanup needed.

    forward.extend(deferred_fk_adds)

    for name in sorted(current_tables - target_tables):
        table = current.tables[name]
        forward.append(DropTable(table=name, schema=table.schema))
        rev_create = _create_table_from_state(name, table)
        reverse.append(rev_create)
        for c in table.constraints:
            reverse.append(
                AddConstraint(table=name, constraint=dict(c), schema=table.schema)
            )
        for idx in table.indexes:
            reverse.append(_create_index_from_state(name, table.schema, idx))

    view_fwd, view_rev = _diff_views(current.views, target.views)

    for name in sorted(current_tables & target_tables):
        cur_t = current.tables[name]
        tgt_t = target.tables[name]
        col_fwd, col_rev = _diff_columns(
            name, tgt_t.schema, cur_t.columns, tgt_t.columns
        )
        forward.extend(col_fwd)
        reverse.extend(col_rev)
        cons_fwd, cons_rev = _diff_constraints(
            name, tgt_t.schema, cur_t.constraints, tgt_t.constraints
        )
        forward.extend(cons_fwd)
        reverse.extend(cons_rev)
        idx_fwd, idx_rev = _diff_indexes(
            name, tgt_t.schema, cur_t.indexes, tgt_t.indexes
        )
        forward.extend(idx_fwd)
        reverse.extend(idx_rev)

    forward.extend(view_fwd)
    reverse.extend(view_rev)

    return forward, reverse


def _create_view_from_state(name: str, view: ViewState) -> CreateView:
    return CreateView(
        name=name,
        definition=view.definition,
        schema=view.schema,
        columns=view.columns,
        replace=True,
    )


def _diff_views(
    current: dict[str, ViewState], target: dict[str, ViewState]
) -> tuple[list, list]:
    forward: list = []
    reverse: list = []

    for name in sorted(set(target) - set(current)):
        v = target[name]
        forward.append(_create_view_from_state(name, v))
        reverse.append(DropView(name=name, schema=v.schema))

    for name in sorted(set(current) - set(target)):
        v = current[name]
        forward.append(DropView(name=name, schema=v.schema))
        reverse.append(_create_view_from_state(name, v))

    for name in sorted(set(current) & set(target)):
        cur = current[name]
        tgt = target[name]
        if cur == tgt:
            continue
        if cur.columns != tgt.columns:
            # Column list reshape — must DROP + CREATE.
            forward.append(DropView(name=name, schema=tgt.schema))
            forward.append(_create_view_from_state(name, tgt))
            reverse.append(DropView(name=name, schema=cur.schema))
            reverse.append(_create_view_from_state(name, cur))
        else:
            # Definition only — CREATE OR REPLACE.
            forward.append(_create_view_from_state(name, tgt))
            reverse.append(_create_view_from_state(name, cur))

    return forward, reverse


def _diff_constraints(
    table: str,
    schema: str | None,
    current: list[dict],
    target: list[dict],
) -> tuple[list, list]:
    forward: list = []
    reverse: list = []
    cur_by_name = {c["name"]: c for c in current}
    tgt_by_name = {c["name"]: c for c in target}
    for name, c in tgt_by_name.items():
        if name not in cur_by_name:
            forward.append(AddConstraint(table=table, constraint=dict(c), schema=schema))
            reverse.append(DropConstraint(table=table, name=name, schema=schema))
    for name, c in cur_by_name.items():
        if name not in tgt_by_name:
            forward.append(DropConstraint(table=table, name=name, schema=schema))
            reverse.append(AddConstraint(table=table, constraint=dict(c), schema=schema))
    return forward, reverse


def _create_index_from_state(table: str, schema: str | None, idx: dict) -> CreateIndex:
    return CreateIndex(
        table=table,
        columns=tuple(idx["columns"]),
        name=idx["name"],
        method=idx.get("method"),
        unique=idx.get("unique", False),
        concurrent=True,
        schema=schema,
    )


def _diff_indexes(
    table: str,
    schema: str | None,
    current: list[dict],
    target: list[dict],
) -> tuple[list, list]:
    forward: list = []
    reverse: list = []
    cur_by_name = {i["name"]: i for i in current}
    tgt_by_name = {i["name"]: i for i in target}
    for name, i in tgt_by_name.items():
        if name not in cur_by_name:
            forward.append(_create_index_from_state(table, schema, i))
            reverse.append(
                DropIndex(name=name, concurrent=True, schema=schema, table=table)
            )
    for name, i in cur_by_name.items():
        if name not in tgt_by_name:
            forward.append(
                DropIndex(name=name, concurrent=True, schema=schema, table=table)
            )
            reverse.append(_create_index_from_state(table, schema, i))
    return forward, reverse
