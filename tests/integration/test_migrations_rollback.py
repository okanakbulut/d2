# pyright: basic
"""Integration tests for `rollback` (issue 147)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from d2 import AsyncpgDriver
from d2.migrations.runner import MigrationRunner


PG_DSN = os.getenv("D2_TEST_DSN", "postgresql://d2:d2@localhost:5432/d2_test")


MIGRATION_0001 = '''
from d2.migrations import Migration
from d2.migrations.operations import CreateTable, ColumnDef, DropTable


class Migration(Migration):
    name = "0001_initial"
    dependencies = []
    operations = [
        CreateTable(
            table="d2_rb_widgets",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                "label": ColumnDef(type="TEXT", nullable=False),
            },
        ),
    ]
    reverse_operations = [
        DropTable(table="d2_rb_widgets", schema="public"),
    ]
'''


MIGRATION_0002 = '''
from d2.migrations import Migration
from d2.migrations.operations import AddColumn, DropColumn


class Migration(Migration):
    name = "0002_add_status"
    dependencies = ["0001_initial"]
    operations = [
        AddColumn(table="d2_rb_widgets", column="status", type="TEXT",
                  nullable=True, default=None, schema="public"),
    ]
    reverse_operations = [
        DropColumn(table="d2_rb_widgets", column="status", schema="public"),
    ]
'''


async def _table_exists(pg_conn: Any, schema: str, table: str) -> bool:
    row = await pg_conn.fetchrow(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = $1 AND table_name = $2",
        schema,
        table,
    )
    return row is not None


async def _column_exists(pg_conn: Any, schema: str, table: str, column: str) -> bool:
    row = await pg_conn.fetchrow(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = $1 AND table_name = $2 AND column_name = $3",
        schema, table, column,
    )
    return row is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_rollback_second_migration_reverts_schema_and_tracking_row(
    pg_conn: Any, tmp_path: Path
) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "0001_initial.py").write_text(MIGRATION_0001)
    (tmp_path / "0002_add_status.py").write_text(MIGRATION_0002)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
    applied = await runner.apply()
    assert applied == ["0001_initial", "0002_add_status"]
    assert await _column_exists(pg_conn, "public", "d2_rb_widgets", "status")

    await runner.rollback("0002_add_status")

    assert not await _column_exists(pg_conn, "public", "d2_rb_widgets", "status")
    assert await _table_exists(pg_conn, "public", "d2_rb_widgets")
    applied_after = await runner.applied()
    assert applied_after == ["0001_initial"]

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")


@pytest.mark.asyncio(loop_scope="session")
async def test_rollback_non_most_recent_without_force_refuses(
    pg_conn: Any, tmp_path: Path
) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "0001_initial.py").write_text(MIGRATION_0001)
    (tmp_path / "0002_add_status.py").write_text(MIGRATION_0002)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
    await runner.apply()

    with pytest.raises(RuntimeError, match="not the most recently applied"):
        await runner.rollback("0001_initial")

    # Schema unchanged: both table + status column still present, both rows still tracked.
    assert await _column_exists(pg_conn, "public", "d2_rb_widgets", "status")
    assert await runner.applied() == ["0001_initial", "0002_add_status"]

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")


def _run_cli(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{workdir}{os.pathsep}{repo_root}"
    return subprocess.run(
        [sys.executable, "-m", "d2.migrations", *args],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cli_rollback_subcommand_dispatches(
    pg_conn: Any, tmp_path: Path
) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "pyproject.toml").write_text(
        '[tool.d2]\nmigrations_dir = "migrations"\nmodels = "models"\n'
    )
    (tmp_path / "models.py").write_text("")
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_initial.py").write_text(MIGRATION_0001)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(migrations_dir))
    await runner.apply()
    assert await _table_exists(pg_conn, "public", "d2_rb_widgets")

    proc = _run_cli(tmp_path, "rollback", "0001_initial", "--dsn", PG_DSN)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert not await _table_exists(pg_conn, "public", "d2_rb_widgets")
    assert await runner.applied() == []

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_rb_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
