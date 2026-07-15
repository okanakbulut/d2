# pyright: basic
"""Integration tests for MigrationRunner against a live PostgreSQL instance."""

from pathlib import Path
from typing import Any

import pytest

from d2 import AsyncpgDriver
from d2.migrations.runner import MigrationRunner


MIGRATION_0001 = '''
from d2.migrations import Migration
from d2.migrations.operations import CreateTable, ColumnDef


class Migration(Migration):
    name = "0001_initial"
    operations = [
        CreateTable(
            table="d2_mig_widgets",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True),
                "label": ColumnDef(type="TEXT", nullable=False),
            },
        ),
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


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_applies_pending_creates_table_and_records_migration(
    pg_conn: Any, tmp_path: Path
) -> None:
    # Clean slate
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_mig_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "0001_initial.py").write_text(MIGRATION_0001)

    conn = AsyncpgDriver(pg_conn)
    runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))

    pending_before = await runner.pending()
    assert pending_before == ["0001_initial"]
    applied_before = await runner.applied()
    assert applied_before == []

    applied_now = await runner.apply()
    assert applied_now == ["0001_initial"]

    assert await _table_exists(pg_conn, "public", "d2_mig_widgets")
    assert await _table_exists(pg_conn, "public", "d2_migrations")

    applied_after = await runner.applied()
    assert applied_after == ["0001_initial"]
    pending_after = await runner.pending()
    assert pending_after == []

    # Second apply is a no-op
    applied_second = await runner.apply()
    assert applied_second == []

    # Cleanup
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_mig_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
