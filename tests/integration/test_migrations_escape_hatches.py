# pyright: basic
"""Integration tests for RunSQL / RunPython escape hatches (issue 148)."""

import os
from pathlib import Path
from typing import Any

import pytest

from d2 import AsyncpgDriver
from d2.migrations.runner import MigrationRunner


PG_DSN = os.getenv("D2_TEST_DSN", "postgresql://d2:d2@localhost:5432/d2_test")


MIGRATION_CREATE = '''
from d2.migrations import Migration
from d2.migrations.operations import CreateTable, ColumnDef, DropTable


class Migration(Migration):
    name = "0001_create"
    dependencies = []
    operations = [
        CreateTable(
            table="d2_eh_widgets",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                "label": ColumnDef(type="TEXT", nullable=True),
            },
        ),
    ]
    reverse_operations = [
        DropTable(table="d2_eh_widgets", schema="public"),
    ]
'''


MIGRATION_BACKFILL = '''
from d2.migrations import Migration
from d2.migrations.operations import RunPython


async def _forward(conn):
    raw = conn._conn
    await raw.execute(
        "INSERT INTO public.d2_eh_widgets (id, label) VALUES (1, 'alpha'), (2, 'beta')"
    )


async def _reverse(conn):
    raw = conn._conn
    await raw.execute("DELETE FROM public.d2_eh_widgets WHERE id IN (1, 2)")


class Migration(Migration):
    name = "0002_backfill"
    dependencies = ["0001_create"]
    operations = [RunPython(fn=_forward, reverse_fn=_reverse)]
    reverse_operations = [RunPython(fn=_forward, reverse_fn=_reverse)]
'''


@pytest.mark.asyncio(loop_scope="session")
async def test_run_python_apply_runs_fn_and_rollback_runs_reverse(
    pg_conn: Any, tmp_path: Path
) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_eh_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "0001_create.py").write_text(MIGRATION_CREATE)
    (tmp_path / "0002_backfill.py").write_text(MIGRATION_BACKFILL)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
    applied = await runner.apply()
    assert applied == ["0001_create", "0002_backfill"]

    rows = await pg_conn.fetch(
        "SELECT id, label FROM public.d2_eh_widgets ORDER BY id"
    )
    assert [(r["id"], r["label"]) for r in rows] == [(1, "alpha"), (2, "beta")]

    await runner.rollback("0002_backfill")

    rows_after = await pg_conn.fetch(
        "SELECT id FROM public.d2_eh_widgets ORDER BY id"
    )
    assert list(rows_after) == []
    assert await runner.applied() == ["0001_create"]

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_eh_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")


MIGRATION_RUNSQL_SEED = '''
from d2.migrations import Migration
from d2.migrations.operations import RunSQL


class Migration(Migration):
    name = "0002_seed"
    dependencies = ["0001_create"]
    operations = [
        RunSQL(
            sql=(
                "INSERT INTO public.d2_eh_widgets (id, label) VALUES (10, 'x');"
                " INSERT INTO public.d2_eh_widgets (id, label) VALUES (20, 'y')"
            ),
            reverse_sql="DELETE FROM public.d2_eh_widgets WHERE id IN (10, 20)",
        ),
    ]
    reverse_operations = [
        RunSQL(
            sql=(
                "INSERT INTO public.d2_eh_widgets (id, label) VALUES (10, 'x');"
                " INSERT INTO public.d2_eh_widgets (id, label) VALUES (20, 'y')"
            ),
            reverse_sql="DELETE FROM public.d2_eh_widgets WHERE id IN (10, 20)",
        ),
    ]
'''


@pytest.mark.asyncio(loop_scope="session")
async def test_run_sql_splits_statements_and_rollback_runs_reverse_sql(
    pg_conn: Any, tmp_path: Path
) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_eh_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "0001_create.py").write_text(MIGRATION_CREATE)
    (tmp_path / "0002_seed.py").write_text(MIGRATION_RUNSQL_SEED)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
    await runner.apply()

    rows = await pg_conn.fetch(
        "SELECT id FROM public.d2_eh_widgets ORDER BY id"
    )
    assert [r["id"] for r in rows] == [10, 20]

    await runner.rollback("0002_seed")

    rows_after = await pg_conn.fetch(
        "SELECT id FROM public.d2_eh_widgets ORDER BY id"
    )
    assert list(rows_after) == []

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_eh_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
