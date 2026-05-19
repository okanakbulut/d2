"""Codegen: write a migration file from a (forward, reverse) op list."""


from pathlib import Path

from .operations import (
    CreateIndex,
    CreateView,
    DropIndex,
    OP_REGISTRY,
    Operation,
)


def is_non_transactional(op: Operation) -> bool:
    if isinstance(op, CreateIndex) and op.concurrent:
        return True
    if isinstance(op, DropIndex) and op.concurrent:
        return True
    return False


# RunSQL/RunPython cannot be serialized via to_source() so they are excluded
# from the import line written into generated migration files. They remain in
# the registry so they can be imported explicitly by hand-authored migrations.
# ColumnDef is a plain alias (not in the registry) but is referenced in the
# source output of CreateTable, so it is always included in the import line.
_SERIALIZABLE_NAMES = sorted(
    {name for name in OP_REGISTRY if name not in ("RunSQL", "RunPython")}
    | {"ColumnDef"}
)
IMPORT_NAMES = ", ".join(_SERIALIZABLE_NAMES)


def derive_label(forward: list[Operation]) -> str:
    from .operations import CreateTable, DropTable
    if len(forward) == 1:
        op = forward[0]
        if isinstance(op, CreateTable):
            return f"create_{op.table}"
        if isinstance(op, DropTable):
            return f"drop_{op.table}"
    return "auto"


def format_op(op: Operation, indent: str) -> str:
    return op.to_source(indent)


def render(
    name: str,
    dependencies: list[str],
    forward: list[Operation],
    reverse: list[Operation],
) -> str:
    non_atomic = any(is_non_transactional(op) for op in forward) or any(
        is_non_transactional(op) for op in reverse
    )

    extra_modules: set[str] = set()
    for op in list(forward) + list(reverse):
        if isinstance(op, CreateView):
            for _, t in op.columns:
                mod = getattr(t, "__module__", "builtins")
                if mod != "builtins":
                    extra_modules.add(mod)

    lines: list[str] = []
    lines.append("from norm.migrations import Migration")
    lines.append(f"from norm.migrations.operations import {IMPORT_NAMES}")
    for mod in sorted(extra_modules):
        lines.append(f"import {mod}")
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
        lines.append(format_op(op, "        "))
    lines.append("    ]")
    lines.append("    reverse_operations = [")
    for op in reverse:
        lines.append(format_op(op, "        "))
    lines.append("    ]")
    lines.append("")
    return "\n".join(lines)


def make_migration(
    *,
    migrations_dir: Path,
    number: int,
    forward: list[Operation],
    reverse: list[Operation],
    dependencies: list[str],
    label: str | None,
) -> Path:
    """Write a migration `.py` file and return its path."""
    resolved_label = label if label else derive_label(forward)
    name = f"{number:04d}_{resolved_label}"
    path = migrations_dir / f"{name}.py"
    path.write_text(render(name, dependencies, forward, reverse))
    return path
