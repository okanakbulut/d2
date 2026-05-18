"""Codegen: write a migration file from a (forward, reverse) op list."""

from __future__ import annotations

from pathlib import Path

from .operations import ColumnDef, CreateTable, DropTable


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


def _format_op(op: object, indent: str) -> str:
    if isinstance(op, CreateTable):
        return _format_create_table(op, indent)
    if isinstance(op, DropTable):
        return _format_drop_table(op, indent)
    raise TypeError(f"codegen does not support op type {type(op).__name__}")


def _render(
    name: str,
    dependencies: list[str],
    forward: list,
    reverse: list,
) -> str:
    lines: list[str] = []
    lines.append("from norm.migrations import Migration")
    lines.append("from norm.migrations.operations import ColumnDef, CreateTable, DropTable")
    lines.append("")
    lines.append("")
    lines.append("class Migration(Migration):")
    lines.append(f'    name = "{name}"')
    dep_items = ", ".join(f'"{d}"' for d in dependencies)
    lines.append(f"    dependencies = [{dep_items}]")
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
