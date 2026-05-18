"""Codegen: write a migration file from a (forward, reverse) op list."""

from __future__ import annotations

from pathlib import Path

from .operations import (
    AddColumn,
    AddConstraint,
    AlterColumnType,
    ColumnDef,
    CreateIndex,
    CreateTable,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropConstraint,
    DropIndex,
    DropTable,
    RenameColumn,
    SetColumnDefault,
    SetColumnNotNull,
)


# All op classes the codegen can emit, used both for `isinstance` dispatch and
# for the migration file's `from norm.migrations.operations import ...` line.
_SUPPORTED_OPS: tuple[type, ...] = (
    AddColumn,
    AddConstraint,
    AlterColumnType,
    ColumnDef,
    CreateIndex,
    CreateTable,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropConstraint,
    DropIndex,
    DropTable,
    RenameColumn,
    SetColumnDefault,
    SetColumnNotNull,
)


def _is_non_transactional(op: object) -> bool:
    if isinstance(op, CreateIndex) and op.concurrent:
        return True
    if isinstance(op, DropIndex) and op.concurrent:
        return True
    return False
_IMPORT_NAMES = ", ".join(sorted(c.__name__ for c in _SUPPORTED_OPS))


def _q(value: object) -> str:
    """Render a Python literal preferring double-quoted strings."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        # Use json-style escapes; bare double quotes inside need escaping.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return repr(value)


def _derive_label(forward: list) -> str:
    if len(forward) == 1:
        op = forward[0]
        if isinstance(op, CreateTable):
            return f"create_{op.table}"
        if isinstance(op, DropTable):
            return f"drop_{op.table}"
    return "auto"


def _format_columndef(cd: ColumnDef) -> str:
    return (
        f"ColumnDef(type={_q(cd.type)}, nullable={_q(cd.nullable)}, "
        f"default={_q(cd.default)}, primary_key={_q(cd.primary_key)})"
    )


def _format_create_table(op: CreateTable, indent: str) -> str:
    lines = [f"{indent}CreateTable("]
    lines.append(f"{indent}    table={_q(op.table)},")
    lines.append(f"{indent}    schema={_q(op.schema)},")
    lines.append(f"{indent}    columns={{")
    for col_name, cd in op.columns.items():
        lines.append(f"{indent}        {_q(col_name)}: {_format_columndef(cd)},")
    lines.append(f"{indent}    }},")
    lines.append(f"{indent}),")
    return "\n".join(lines)


def _format_drop_table(op: DropTable, indent: str) -> str:
    return f"{indent}DropTable(table={_q(op.table)}, schema={_q(op.schema)}),"


def _format_add_column(op: AddColumn, indent: str) -> str:
    return (
        f"{indent}AddColumn(table={_q(op.table)}, column={_q(op.column)}, "
        f"type={_q(op.type)}, nullable={_q(op.nullable)}, "
        f"default={_q(op.default)}, schema={_q(op.schema)}),"
    )


def _format_drop_column(op: DropColumn, indent: str) -> str:
    return (
        f"{indent}DropColumn(table={_q(op.table)}, column={_q(op.column)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_rename_column(op: RenameColumn, indent: str) -> str:
    return (
        f"{indent}RenameColumn(table={_q(op.table)}, "
        f"old_name={_q(op.old_name)}, new_name={_q(op.new_name)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_alter_column_type(op: AlterColumnType, indent: str) -> str:
    return (
        f"{indent}AlterColumnType(table={_q(op.table)}, column={_q(op.column)}, "
        f"type={_q(op.type)}, schema={_q(op.schema)}),"
    )


def _format_set_not_null(op: SetColumnNotNull, indent: str) -> str:
    return (
        f"{indent}SetColumnNotNull(table={_q(op.table)}, column={_q(op.column)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_drop_not_null(op: DropColumnNotNull, indent: str) -> str:
    return (
        f"{indent}DropColumnNotNull(table={_q(op.table)}, column={_q(op.column)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_set_default(op: SetColumnDefault, indent: str) -> str:
    return (
        f"{indent}SetColumnDefault(table={_q(op.table)}, column={_q(op.column)}, "
        f"default={_q(op.default)}, schema={_q(op.schema)}),"
    )


def _format_drop_default(op: DropColumnDefault, indent: str) -> str:
    return (
        f"{indent}DropColumnDefault(table={_q(op.table)}, column={_q(op.column)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_constraint_dict(c: dict) -> str:
    cols = "(" + ", ".join(_q(x) for x in c["columns"]) + (",)" if len(c["columns"]) == 1 else ")")
    parts = [
        f'"type": {_q(c["type"])}',
        f'"name": {_q(c["name"])}',
        f'"columns": {cols}',
    ]
    if c["type"] == "foreign_key":
        parts.append(f'"references_schema": {_q(c.get("references_schema"))}')
        parts.append(f'"references_table": {_q(c["references_table"])}')
        parts.append(f'"references_column": {_q(c["references_column"])}')
        parts.append(f'"on_delete": {_q(c.get("on_delete"))}')
        parts.append(f'"on_update": {_q(c.get("on_update"))}')
    return "{" + ", ".join(parts) + "}"


def _format_add_constraint(op: AddConstraint, indent: str) -> str:
    return (
        f"{indent}AddConstraint(table={_q(op.table)}, "
        f"constraint={_format_constraint_dict(op.constraint)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_drop_constraint(op: DropConstraint, indent: str) -> str:
    return (
        f"{indent}DropConstraint(table={_q(op.table)}, name={_q(op.name)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_columns_tuple(cols: tuple[str, ...]) -> str:
    inside = ", ".join(_q(c) for c in cols)
    if len(cols) == 1:
        return f"({inside},)"
    return f"({inside})"


def _format_create_index(op: CreateIndex, indent: str) -> str:
    return (
        f"{indent}CreateIndex(table={_q(op.table)}, "
        f"columns={_format_columns_tuple(tuple(op.columns))}, "
        f"name={_q(op.name)}, method={_q(op.method)}, "
        f"unique={_q(op.unique)}, concurrent={_q(op.concurrent)}, "
        f"schema={_q(op.schema)}),"
    )


def _format_drop_index(op: DropIndex, indent: str) -> str:
    return (
        f"{indent}DropIndex(name={_q(op.name)}, concurrent={_q(op.concurrent)}, "
        f"schema={_q(op.schema)}, table={_q(op.table)}),"
    )


def _format_op(op: object, indent: str) -> str:
    if isinstance(op, CreateTable):
        return _format_create_table(op, indent)
    if isinstance(op, DropTable):
        return _format_drop_table(op, indent)
    if isinstance(op, AddColumn):
        return _format_add_column(op, indent)
    if isinstance(op, DropColumn):
        return _format_drop_column(op, indent)
    if isinstance(op, RenameColumn):
        return _format_rename_column(op, indent)
    if isinstance(op, AlterColumnType):
        return _format_alter_column_type(op, indent)
    if isinstance(op, SetColumnNotNull):
        return _format_set_not_null(op, indent)
    if isinstance(op, DropColumnNotNull):
        return _format_drop_not_null(op, indent)
    if isinstance(op, SetColumnDefault):
        return _format_set_default(op, indent)
    if isinstance(op, DropColumnDefault):
        return _format_drop_default(op, indent)
    if isinstance(op, AddConstraint):
        return _format_add_constraint(op, indent)
    if isinstance(op, DropConstraint):
        return _format_drop_constraint(op, indent)
    if isinstance(op, CreateIndex):
        return _format_create_index(op, indent)
    if isinstance(op, DropIndex):
        return _format_drop_index(op, indent)
    raise TypeError(f"codegen does not support op type {type(op).__name__}")


def _render(
    name: str,
    dependencies: list[str],
    forward: list,
    reverse: list,
) -> str:
    non_atomic = any(_is_non_transactional(op) for op in forward) or any(
        _is_non_transactional(op) for op in reverse
    )

    lines: list[str] = []
    lines.append("from norm.migrations import Migration")
    lines.append(f"from norm.migrations.operations import {_IMPORT_NAMES}")
    lines.append("")
    if non_atomic:
        lines.append(
            "# atomic = False because this migration contains "
            "non-transactional operations (CONCURRENTLY)."
        )
    lines.append("")
    lines.append("class Migration(Migration):")
    lines.append(f'    name = "{name}"')
    dep_items = ", ".join(f'"{d}"' for d in dependencies)
    lines.append(f"    dependencies = [{dep_items}]")
    if non_atomic:
        lines.append("    atomic = False")
    lines.append("    operations = [")
    for op in forward:
        lines.append(_format_op(op, "        "))
    lines.append("    ]")
    lines.append("    reverse_operations = [")
    for op in reverse:
        lines.append(_format_op(op, "        "))
    lines.append("    ]")
    lines.append("")
    return "\n".join(lines)


def make_migration(
    *,
    migrations_dir: Path,
    number: int,
    forward: list,
    reverse: list,
    dependencies: list[str],
    label: str | None,
) -> Path:
    """Write a migration `.py` file and return its path."""
    resolved_label = label if label else _derive_label(forward)
    name = f"{number:04d}_{resolved_label}"
    path = migrations_dir / f"{name}.py"
    path.write_text(_render(name, dependencies, forward, reverse))
    return path
