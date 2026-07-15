# pyright: basic
"""Integration test for issue 143: model with unique=True field + IndexDef
produces a non-atomic migration with concurrent=True, and `apply` succeeds."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS = '''
from d2.schema import Table, Field, PrimaryKey
from d2.model import field, IndexDef, TableMeta
from d2 import db


class CIWidget(Table):
    __meta__ = TableMeta(
        table="d2_ci_widgets",
        schema="public",
        indexes=(IndexDef(columns=("score",), name="idx_d2_ci_widgets_score"),),
    )
    id: PrimaryKey[int] = field(default=db.serial())
    email: Field[str] = field(unique=True)
    score: Field[int]
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
async def test_unique_and_index_make_and_apply(pg_conn: Any, tmp_path: Path) -> None:
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_ci_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "models.py").write_text(MODELS)
    (tmp_path / "migrations").mkdir()

    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr

    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert len(files) == 1
    body = files[0].read_text()
    assert "atomic = False" in body
    assert "concurrent=True" in body
    assert (
        'AddConstraint(table="d2_ci_widgets", '
        'constraint={"type": "unique", "name": "d2_ci_widgets_email_key", '
        '"columns": ("email",)}, schema="public"),'
    ) in body
    assert (
        'CreateIndex(table="d2_ci_widgets", columns=("score",), '
        'name="idx_d2_ci_widgets_score", method=None, unique=False, '
        'concurrent=True, schema="public"),'
    ) in body

    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr

    constraint_row = await pg_conn.fetchrow(
        "SELECT conname FROM pg_constraint "
        "WHERE conname = $1",
        "d2_ci_widgets_email_key",
    )
    assert constraint_row is not None

    index_row = await pg_conn.fetchrow(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = $1 AND tablename = $2 AND indexname = $3",
        "public",
        "d2_ci_widgets",
        "idx_d2_ci_widgets_score",
    )
    assert index_row is not None

    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)

    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_ci_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
