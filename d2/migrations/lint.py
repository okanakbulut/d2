"""Lint checks for migration files: atomic/concurrent mismatches and DDL in RunSQL."""

import re
from pathlib import Path

from .config import D2Config
from .discovery import existing_migration_files

DDL_KEYWORDS = ("ALTER", "CREATE", "DROP", "TRUNCATE")


def strip_sql_noise(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            nl = sql.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n:
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def run_sql_contains_ddl(sql: str) -> str | None:
    """Return the first DDL keyword found, else None."""
    cleaned = strip_sql_noise(sql).upper()
    tokens = re.findall(r"[A-Z]+", cleaned)
    for kw in DDL_KEYWORDS:
        if kw in tokens:
            return kw
    return None


def check_atomic_mismatch(cfg: D2Config) -> list[tuple[Path, str]]:
    from .operations import CreateIndex, DropIndex
    from .replay import load_migration

    warnings: list[tuple[Path, str]] = []
    for path in existing_migration_files(cfg.migrations_dir):
        mig_cls = load_migration(path)
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


def check_run_sql_ddl(cfg: D2Config) -> list[tuple[Path, str]]:
    from .operations import RunSQL
    from .replay import load_migration

    warnings: list[tuple[Path, str]] = []
    for path in existing_migration_files(cfg.migrations_dir):
        mig_cls = load_migration(path)
        for op in list(mig_cls.operations) + list(mig_cls.reverse_operations or []):
            if not isinstance(op, RunSQL):
                continue
            kw = run_sql_contains_ddl(op.sql)
            if kw is not None:
                warnings.append(
                    (
                        path,
                        f"{mig_cls.name}: RunSQL contains DDL keyword {kw!r}; "
                        "use a typed DDL op (e.g. AlterColumnType, CreateTable) "
                        "instead so the schema model stays in sync",
                    )
                )
                break
    return warnings
