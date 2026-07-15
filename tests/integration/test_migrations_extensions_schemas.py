# pyright: basic
"""Integration test for issue 146: extensions + schemas in migrations.

A model declares `extensions=("pgcrypto",)` and `schema="audit_146"`; the
generated migration must create the extension and schema in the correct order
before creating the table.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS_SOURCE = '''
from d2.schema import Table, Field, PrimaryKey
from d2.model import field, TableMeta
from d2 import db


class IssueOneFourSixEvent(Table):
    __meta__ = TableMeta(
        table="audit_events_146",
        schema="audit_146",
        extensions=("pgcrypto",),
    )
    id: PrimaryKey[int] = field(default=db.serial())
    label: Field[str]
'''


PYPROJECT = """
[tool.d2]
migrations_dir = "migrations"
models = "models"
"""


PG_DSN = os.getenv("D2_TEST_DSN", "postgresql://d2:d2@localhost:5432/d2_test")


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


async def _table_exists(pg_conn: Any, schema: str, table: str) -> bool:
    row = await pg_conn.fetchrow(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = $1 AND table_name = $2",
        schema,
        table,
    )
    return row is not None


async def _schema_exists(pg_conn: Any, schema: str) -> bool:
    row = await pg_conn.fetchrow(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
        schema,
    )
    return row is not None


async def _extension_installed(pg_conn: Any, name: str) -> bool:
    row = await pg_conn.fetchrow(
        "SELECT 1 FROM pg_extension WHERE extname = $1", name,
    )
    return row is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_extensions_and_schemas_end_to_end(
    pg_conn: Any, tmp_path: Path,
) -> None:
    # Clean slate (drop dependent objects first; pgcrypto may be shared, so do
    # not drop it here — the migration's `apply` uses IF NOT EXISTS anyway).
    await pg_conn.execute("DROP TABLE IF EXISTS audit_146.audit_events_146")
    await pg_conn.execute("DROP SCHEMA IF EXISTS audit_146 CASCADE")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "models.py").write_text(MODELS_SOURCE)
    (tmp_path / "migrations").mkdir()

    # make → generates a migration
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert len(files) == 1
    body = files[0].read_text()

    # Forward order: CreateExtension → CreateSchema → CreateTable.
    ext_pos = body.index('CreateExtension(name="pgcrypto")')
    schema_pos = body.index('CreateSchema(name="audit_146")')
    table_pos = body.index('CreateTable(')
    assert ext_pos < schema_pos < table_pos

    # apply
    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr

    assert await _extension_installed(pg_conn, "pgcrypto")
    assert await _schema_exists(pg_conn, "audit_146")
    assert await _table_exists(pg_conn, "audit_146", "audit_events_146")

    # check → silent, exit 0
    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert proc.stdout == ""

    # cleanup
    await pg_conn.execute("DROP TABLE IF EXISTS audit_146.audit_events_146")
    await pg_conn.execute("DROP SCHEMA IF EXISTS audit_146 CASCADE")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
