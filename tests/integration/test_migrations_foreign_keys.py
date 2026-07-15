# pyright: basic
"""Integration test for issue 144: two tables with an inline FK between them,
`make` emits CreateTable ops first then a deferred FK AddConstraint, and
`apply` succeeds against Postgres."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS = '''
from d2 import Table, Field, ForeignKey, PrimaryKey, db, field
from d2.model import TableMeta


class D2FkOrg(Table):
    __meta__ = TableMeta(table="d2_fk_org", schema="public")
    id: PrimaryKey[int] = field(default=db.serial())


class D2FkUser(Table):
    __meta__ = TableMeta(table="d2_fk_user", schema="public")
    id: PrimaryKey[int] = field(default=db.serial())
    org_id: ForeignKey[D2FkOrg] = field(on_delete=db.CASCADE)
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


@pytest.mark.asyncio(loop_scope="session")
async def test_fk_make_and_apply(pg_conn: Any, tmp_path: Path) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_fk_user")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_fk_org")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "models.py").write_text(MODELS)
    (tmp_path / "migrations").mkdir()

    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr

    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert len(files) == 1
    body = files[0].read_text()

    # The forward op list must show both CreateTable ops BEFORE the FK AddConstraint.
    pos_create_org = body.index('CreateTable(\n            table="d2_fk_org"')
    pos_create_user = body.index('CreateTable(\n            table="d2_fk_user"')
    pos_fk = body.index('"type": "foreign_key"')
    assert pos_create_org < pos_fk
    assert pos_create_user < pos_fk

    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr

    constraint_row = await pg_conn.fetchrow(
        "SELECT conname, confrelid::regclass::text AS ref_table "
        "FROM pg_constraint WHERE conname = $1",
        "d2_fk_user_org_id_fkey",
    )
    assert constraint_row is not None
    assert constraint_row["ref_table"] == "d2_fk_org"

    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_fk_user")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_fk_org")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
