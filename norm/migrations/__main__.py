"""Migrations CLI: `python -m norm.migrations {make,apply,check}`."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import pkgutil
import sys
from pathlib import Path

from .codegen import make_migration
from .config import NormConfig, load_config
from .draft import diff_states
from .registry import _MODEL_REGISTRY
from .replay import replay_migrations
from .snapshot import models_to_schema_state


def _import_models_module(dotted: str) -> None:
    if dotted in sys.modules:
        module = importlib.reload(sys.modules[dotted])
    else:
        module = importlib.import_module(dotted)
    # If it's a package, eagerly import submodules so their classes register.
    if hasattr(module, "__path__"):
        for sub in pkgutil.iter_modules(module.__path__):
            full = f"{dotted}.{sub.name}"
            if full in sys.modules:
                importlib.reload(sys.modules[full])
            else:
                importlib.import_module(full)


def _models_for(cfg: NormConfig) -> list[type]:
    prefix = cfg.models
    # Drop any prior registrations under this prefix so a reload reflects the
    # current source-of-truth (important for tests and the long-lived CLI).
    stale = [
        key for key, cls in _MODEL_REGISTRY.items()
        if cls.__module__ == prefix or cls.__module__.startswith(prefix + ".")
    ]
    for key in stale:
        del _MODEL_REGISTRY[key]

    _import_models_module(prefix)

    return [
        cls
        for cls in _MODEL_REGISTRY.values()
        if cls.__module__ == prefix or cls.__module__.startswith(prefix + ".")
    ]


def _existing_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        return []
    return sorted(p for p in migrations_dir.glob("*.py") if not p.name.startswith("_"))


def _next_number(migrations_dir: Path) -> int:
    files = _existing_migration_files(migrations_dir)
    highest = 0
    for p in files:
        head = p.stem.split("_", 1)[0]
        if head.isdigit():
            highest = max(highest, int(head))
    return highest + 1


def _compute_diff(cfg: NormConfig):
    cfg.migrations_dir.mkdir(parents=True, exist_ok=True)
    current = replay_migrations(_existing_migration_files(cfg.migrations_dir))
    target = models_to_schema_state(_models_for(cfg))
    return diff_states(current, target), target


def cmd_make(*, cwd: Path, migrations_dir: str | None = None, models: str | None = None, label: str | None = None) -> int:
    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    (forward, reverse), _ = _compute_diff(cfg)

    if not forward:
        print("No changes detected.")
        return 0

    deps = [p.stem for p in _existing_migration_files(cfg.migrations_dir)]
    number = _next_number(cfg.migrations_dir)
    path = make_migration(
        migrations_dir=cfg.migrations_dir,
        number=number,
        forward=forward,
        reverse=reverse,
        dependencies=deps,
        label=label,
    )
    print(f"Wrote {path}")
    return 0


def cmd_check(*, cwd: Path, migrations_dir: str | None = None, models: str | None = None) -> int:
    try:
        cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
        atomic_warnings = _check_atomic_mismatch(cfg)
        (forward, _reverse), _ = _compute_diff(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"{cwd}:1: migration check failed: {exc}")
        return 2

    if atomic_warnings:
        for path, msg in atomic_warnings:
            print(f"{path}:1: {msg}")
        return 1

    if not forward:
        return 0

    models_file = cwd / (cfg.models.replace(".", "/") + ".py")
    if not models_file.exists():
        models_file = cwd / cfg.models.replace(".", "/") / "__init__.py"
    print(f"{models_file}:1: schema drift detected")
    return 1


def _check_atomic_mismatch(cfg: NormConfig) -> list[tuple[Path, str]]:
    from .operations import CreateIndex, DropIndex
    from .replay import _load_migration

    warnings: list[tuple[Path, str]] = []
    for path in _existing_migration_files(cfg.migrations_dir):
        mig_cls = _load_migration(path)
        if not mig_cls.atomic:
            continue
        has_non_tx = any(
            (isinstance(op, CreateIndex) and op.concurrent)
            or (isinstance(op, DropIndex) and op.concurrent)
            for op in mig_cls.operations
        )
        if has_non_tx:
            warnings.append(
                (
                    path,
                    f"{mig_cls.name}: atomic = True but operations include "
                    "CONCURRENTLY index ops; set atomic = False",
                )
            )
    return warnings


async def cmd_apply(*, cwd: Path, dsn: str, migrations_dir: str | None = None, models: str | None = None) -> int:
    import asyncpg  # local import to keep CLI startup light

    from norm.connection import AsyncConnection
    from .runner import MigrationRunner

    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    raw = await asyncpg.connect(dsn)
    try:
        runner = MigrationRunner(conn=AsyncConnection(raw), migrations_dir=str(cfg.migrations_dir))
        applied = await runner.apply()
    finally:
        await raw.close()
    for name in applied:
        print(f"Applied {name}")
    if not applied:
        print("No pending migrations.")
    return 0


async def cmd_rollback(
    *,
    cwd: Path,
    dsn: str,
    name: str,
    force: bool = False,
    migrations_dir: str | None = None,
    models: str | None = None,
) -> int:
    import asyncpg  # local import to keep CLI startup light

    from norm.connection import AsyncConnection
    from .runner import MigrationRunner

    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    raw = await asyncpg.connect(dsn)
    try:
        runner = MigrationRunner(conn=AsyncConnection(raw), migrations_dir=str(cfg.migrations_dir))
        await runner.rollback(name, force=force)
    finally:
        await raw.close()
    print(f"Rolled back {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="norm.migrations")
    parser.add_argument("--migrations-dir", default=None)
    parser.add_argument("--models", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make")
    sub.add_parser("check")
    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--dsn", required=True)
    rollback_p = sub.add_parser("rollback")
    rollback_p.add_argument("name")
    rollback_p.add_argument("--dsn", required=True)
    rollback_p.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    cwd = Path.cwd()
    sys.path.insert(0, str(cwd))

    if args.cmd == "make":
        return cmd_make(cwd=cwd, migrations_dir=args.migrations_dir, models=args.models)
    if args.cmd == "check":
        return cmd_check(cwd=cwd, migrations_dir=args.migrations_dir, models=args.models)
    if args.cmd == "apply":
        return asyncio.run(
            cmd_apply(cwd=cwd, dsn=args.dsn, migrations_dir=args.migrations_dir, models=args.models)
        )
    if args.cmd == "rollback":
        return asyncio.run(
            cmd_rollback(
                cwd=cwd,
                dsn=args.dsn,
                name=args.name,
                force=args.force,
                migrations_dir=args.migrations_dir,
                models=args.models,
            )
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
