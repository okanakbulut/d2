# pyright: basic
"""Integration test: add a field to an existing model and verify `make` + `apply`
emits and runs an AddColumn op (issue 142)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


MODELS_INITIAL = '''
from d2.schema import Table, Field, PrimaryKey
from d2.model import field, TableMeta
from d2 import db


class ColOpWidget(Table):
    __meta__ = TableMeta(table="d2_colop_widgets", schema="public")
    id: PrimaryKey[int] = field(default=db.serial())
    label: Field[str]
'''


MODELS_WITH_ADDED_FIELD = '''
from d2.schema import Table, Field, PrimaryKey
from d2.model import field, TableMeta
from d2 import db


class ColOpWidget(Table):
    __meta__ = TableMeta(table="d2_colop_widgets", schema="public")
    id: PrimaryKey[int] = field(default=db.serial())
    label: Field[str]
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


async def _column_info(pg_conn: Any, schema: str, table: str, column: str) -> dict | None:
    row = await pg_conn.fetchrow(
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = $1 AND table_name = $2 AND column_name = $3",
        schema,
        table,
        column,
    )
    if row is None:
        return None
    return {"data_type": row["data_type"], "is_nullable": row["is_nullable"]}


@pytest.mark.asyncio(loop_scope="session")
async def test_add_field_makes_and_applies_add_column(pg_conn: Any, tmp_path: Path) -> None:
    # Clean slate
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_colop_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")

    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "models.py").write_text(MODELS_INITIAL)
    (tmp_path / "migrations").mkdir()

    # 1. make initial migration
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert [p.name for p in files] == ["0001_create_d2_colop_widgets.py"]

    # 2. apply: table exists, score column does not
    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr
    assert await _column_info(pg_conn, "public", "d2_colop_widgets", "score") is None

    # 3. add field to model and `make` again
    (tmp_path / "models.py").write_text(MODELS_WITH_ADDED_FIELD)
    proc = _run_cli(tmp_path, "make")
    assert proc.returncode == 0, proc.stderr
    files = sorted((tmp_path / "migrations").glob("*.py"))
    assert [p.name for p in files] == [
        "0001_create_d2_colop_widgets.py",
        "0002_auto.py",
    ]
    second = (tmp_path / "migrations" / "0002_auto.py").read_text()
    assert 'AddColumn(table="d2_colop_widgets", column="score", type="BIGINT", nullable=False, default=None, schema="public")' in second
    assert 'DropColumn(table="d2_colop_widgets", column="score", schema="public")' in second

    # 4. apply: score column now exists with correct type & nullability
    proc = _run_cli(tmp_path, "apply", "--dsn", PG_DSN)
    assert proc.returncode == 0, proc.stderr
    info = await _column_info(pg_conn, "public", "d2_colop_widgets", "score")
    assert info == {"data_type": "bigint", "is_nullable": "NO"}

    # 5. check is clean
    proc = _run_cli(tmp_path, "check")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert proc.stdout == ""

    # cleanup
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_colop_widgets")
    await pg_conn.execute("DROP TABLE IF EXISTS public.d2_migrations")
