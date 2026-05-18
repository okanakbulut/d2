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
    AlterColumnType,
    ColumnDef,
    CreateTable,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropTable,
    SetColumnDefault,
    SetColumnNotNull,
)
from .state import ColumnState, SchemaState, TableState


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

    for name in sorted(target_tables - current_tables):
        table = target.tables[name]
        forward.append(_create_table_from_state(name, table))
        reverse.append(DropTable(table=name, schema=table.schema))

    for name in sorted(current_tables - target_tables):
        table = current.tables[name]
        forward.append(DropTable(table=name, schema=table.schema))
        reverse.append(_create_table_from_state(name, table))

    for name in sorted(current_tables & target_tables):
        cur_t = current.tables[name]
        tgt_t = target.tables[name]
        col_fwd, col_rev = _diff_columns(
            name, tgt_t.schema, cur_t.columns, tgt_t.columns
        )
        forward.extend(col_fwd)
        reverse.extend(col_rev)

    return forward, reverse
