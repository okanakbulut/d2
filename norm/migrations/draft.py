"""Diff two `SchemaState`s into a pair of forward/reverse operation lists.

Issue 141 scope: detect new/dropped tables only. Column-level diffs (add/drop/
modify) are deferred to issue 142.
"""

from __future__ import annotations

from .operations import ColumnDef, CreateTable, DropTable
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

    return forward, reverse
