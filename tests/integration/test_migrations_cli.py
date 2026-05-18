# pyright: basic
"""Integration test: declare a model → make → apply → check (e2e)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS_SOURCE = '''
from norm.schema import Table, Field, PrimaryKey
from norm.model import field, TableMeta


class CliIntWidget(Table):
    __meta__ = TableMeta(table="norm_cli_widgets", schema="public")
    id: PrimaryKey[int] = field(db_default=True)
    label: Field[str]
'''


PYPROJECT = """
[tool.norm]
migrations_dir = "migrations"
models = "models"
"""


PG_DSN = os.getenv("NORM_TEST_DSN", "postgresql://norm:norm@localhost:5432/norm_test")


def _run_cli(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{workdir}{os.pathsep}{repo_root}"
    return subprocess.run(
        [sys.executable, "-m", "norm.migrations", *args],
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


@pytest.mark.asyncio(loop_scope="session")
async def test_make_apply_check_end_to_end(pg_conn: Any, tmp_path: Path) -> None:
    # Clean slate
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_cli_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "models.py").write_text(MODELS_SOURCE)
    (tmp_path / "migrations").mkdir()

    # 1. make → creates 0001_create_norm_cli_widgets.py
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert [p.name for p in files] == ["0001_create_norm_cli_widgets.py"]

    # 2. apply → table appears
    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr
    assert await _table_exists(pg_conn, "public", "norm_cli_widgets")

    # 3. check → silent, exit 0
    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert proc.stdout == ""

    # cleanup
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_cli_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_migrations")
