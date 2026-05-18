# pyright: basic
"""Integration test for view declaration + make + apply (issue 145)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS_V1 = '''
from norm.schema import Table, Field, PrimaryKey, View
from norm.model import field, TableMeta


class ViewUsers(Table):
    __meta__ = TableMeta(table="norm_view_users", schema="public")
    id: PrimaryKey[int] = field(db_default=True)
    email: Field[str]
    deleted: Field[bool]


_active = ViewUsers.select(ViewUsers.id, ViewUsers.email).where(ViewUsers.deleted == False)


class ActiveViewUsers(View, query=_active):
    __meta__ = TableMeta(table="norm_active_view_users", schema="public")
    id: PrimaryKey[int]
    email: Field[str]
'''


MODELS_V2 = '''
from norm.schema import Table, Field, PrimaryKey, View
from norm.model import field, TableMeta


class ViewUsers(Table):
    __meta__ = TableMeta(table="norm_view_users", schema="public")
    id: PrimaryKey[int] = field(db_default=True)
    email: Field[str]
    deleted: Field[bool]


# Same column shape; different WHERE clause → definition-only change.
_active = ViewUsers.select(ViewUsers.id, ViewUsers.email).where(ViewUsers.id > 0)


class ActiveViewUsers(View, query=_active):
    __meta__ = TableMeta(table="norm_active_view_users", schema="public")
    id: PrimaryKey[int]
    email: Field[str]
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


async def _view_definition(pg_conn: Any, schema: str, name: str) -> str | None:
    row = await pg_conn.fetchrow(
        "SELECT view_definition FROM information_schema.views "
        "WHERE table_schema = $1 AND table_name = $2",
        schema,
        name,
    )
    return None if row is None else row[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_view_make_apply_then_replace(pg_conn: Any, tmp_path: Path) -> None:
    # Clean slate
    await pg_conn.execute("DROP VIEW IF EXISTS public.norm_active_view_users")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_view_users")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    models_path = tmp_path / "models.py"
    models_path.write_text(MODELS_V1)
    (tmp_path / "migrations").mkdir()

    # 1. make initial
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files_v1 = sorted((tmp_path / "migrations").glob("*.py"))
    assert len(files_v1) == 1

    # 2. apply → table + view exist
    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr

    defn_v1 = await _view_definition(pg_conn, "public", "norm_active_view_users")
    assert defn_v1 is not None

    # 3. populate base table and query through the view
    await pg_conn.execute(
        "INSERT INTO public.norm_view_users (id, email, deleted) VALUES "
        "(1, 'a@x', false), (2, 'b@x', true)"
    )
    rows = await pg_conn.fetch(
        'SELECT "email" FROM public.norm_active_view_users ORDER BY "email"'
    )
    assert [r[0] for r in rows] == ["a@x"]

    # 4. change the WHERE clause → second migration applies CREATE OR REPLACE VIEW
    models_path.write_text(MODELS_V2)
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files_v2 = sorted((tmp_path / "migrations").glob("*.py"))
    assert len(files_v2) == 2

    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr

    defn_v2 = await _view_definition(pg_conn, "public", "norm_active_view_users")
    assert defn_v2 is not None
    assert defn_v2 != defn_v1

    # 5. check is silent
    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert proc.stdout == ""

    # Cleanup
    await pg_conn.execute("DROP VIEW IF EXISTS public.norm_active_view_users")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_view_users")
    await pg_conn.execute("DROP TABLE IF EXISTS public.norm_migrations")
