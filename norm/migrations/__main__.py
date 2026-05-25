"""Migrations CLI: `python -m norm.migrations {make,apply,check}`."""


import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from .codegen import make_migration
from .config import NormConfig, load_config
from .discovery import existing_migration_files, models_for, next_number
from .lint import check_atomic_mismatch, check_run_sql_ddl
from .pipeline import SchemaPipeline


def compute_pipeline(cfg: NormConfig) -> SchemaPipeline:
    cfg.migrations_dir.mkdir(parents=True, exist_ok=True)
    files = existing_migration_files(cfg.migrations_dir)
    models = models_for(cfg)
    return SchemaPipeline.build(migration_files=files, models=models)


def cmd_make(*, cwd: Path, migrations_dir: str | None = None, models: str | None = None, label: str | None = None) -> int:
    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    pipeline = compute_pipeline(cfg)

    if not pipeline.has_changes:
        print("No changes detected.")
        return 0

    deps = [p.stem for p in existing_migration_files(cfg.migrations_dir)]
    number = next_number(cfg.migrations_dir)
    path = make_migration(
        migrations_dir=cfg.migrations_dir,
        number=number,
        forward=pipeline.forward,
        reverse=pipeline.reverse,
        dependencies=deps,
        label=label,
    )
    print(f"Wrote {path}")
    return 0


def cmd_check(*, cwd: Path, migrations_dir: str | None = None, models: str | None = None) -> int:
    try:
        cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
        atomic_warnings = check_atomic_mismatch(cfg)
        ddl_warnings = check_run_sql_ddl(cfg)
        pipeline = compute_pipeline(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"{cwd}:1: migration check failed: {exc}")
        return 2

    if atomic_warnings or ddl_warnings:
        for path, msg in atomic_warnings + ddl_warnings:
            print(f"{path}:1: {msg}")
        return 1

    if not pipeline.has_changes:
        return 0

    models_file = cwd / (cfg.models.replace(".", "/") + ".py")
    if not models_file.exists():
        models_file = cwd / cfg.models.replace(".", "/") / "__init__.py"
    print(f"{models_file}:1: schema drift detected")
    return 1


async def cmd_apply(*, cwd: Path, dsn: str, migrations_dir: str | None = None, models: str | None = None) -> int:
    import asyncpg  # local import to keep CLI startup light

    from norm.connection import AsyncpgDriver
    from .runner import MigrationRunner

    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    asyncpg_any: Any = asyncpg
    raw: Any = await asyncpg_any.connect(dsn)
    try:
        runner = MigrationRunner(conn=AsyncpgDriver(raw), migrations_dir=str(cfg.migrations_dir))
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

    from norm.connection import AsyncpgDriver
    from .runner import MigrationRunner

    cfg = load_config(cwd, migrations_dir_override=migrations_dir, models_override=models)
    asyncpg_any: Any = asyncpg
    raw: Any = await asyncpg_any.connect(dsn)
    try:
        runner = MigrationRunner(conn=AsyncpgDriver(raw), migrations_dir=str(cfg.migrations_dir))
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
