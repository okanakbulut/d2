"""Unit tests for MigrationRunner non-atomic CONCURRENTLY recovery (issue 143)."""


from pathlib import Path
from typing import ClassVar

import pytest

from typing import Any

from norm.migrations import Migration
from norm.migrations.operations import CreateIndex, Operation
from norm.migrations.runner import MigrationRunner


class _StubRaw:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.executed: list[str] = []
        self._fail_on = fail_on
        self.txn_entered = 0

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append(sql)
        if self._fail_on is not None and self._fail_on in sql:
            raise RuntimeError("simulated CONCURRENTLY failure")

    async def fetch(self, sql: str, *args: object) -> list[dict[str, str]]:
        return []

    def transaction(self) -> "_StubRaw":
        return self

    async def __aenter__(self) -> "_StubRaw":
        self.txn_entered += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _StubConn:
    def __init__(self, raw: _StubRaw) -> None:
        self._conn = raw

    async def execute(self, sql: str, *args: object) -> list[Any]:
        if sql.strip().upper().startswith("SELECT"):
            return list(await self._conn.fetch(sql, *args))
        await self._conn.execute(sql, *args)
        return []

    def transaction(self) -> _StubRaw:
        return self._conn.transaction()


class _NonAtomicMig(Migration):
    name = "0001_non_atomic"
    atomic = False
    operations: ClassVar[list[Operation]] = [
        CreateIndex(
            table="t",
            columns=("x",),
            name="idx_t_x",
            concurrent=True,
            schema="public",
        ),
    ]


@pytest.mark.asyncio
async def test_non_atomic_migration_is_not_wrapped_in_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _StubRaw()
    runner = MigrationRunner(
        conn=_StubConn(raw), migrations_dir=str(tmp_path)
    )

    # Bypass file discovery by patching _discover.
    monkeypatch.setattr(
        runner, "_discover", lambda: [("0001_non_atomic", _NonAtomicMig)]
    )

    await runner.apply()

    assert raw.txn_entered == 0
    create_tracking_sql = (
        "CREATE TABLE IF NOT EXISTS norm_migrations ("
        "id SERIAL PRIMARY KEY, "
        "name TEXT NOT NULL UNIQUE, "
        "applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    assert raw.executed == [
        create_tracking_sql,
        create_tracking_sql,
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_t_x" ON "public"."t" ("x")',
        "INSERT INTO norm_migrations (name) VALUES ($1)",
    ]


@pytest.mark.asyncio
async def test_concurrently_failure_prints_recovery_and_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _StubRaw(fail_on="CREATE INDEX CONCURRENTLY")
    runner = MigrationRunner(
        conn=_StubConn(raw), migrations_dir=str(tmp_path)
    )

    monkeypatch.setattr(
        runner, "_discover", lambda: [("0001_non_atomic", _NonAtomicMig)]
    )

    with pytest.raises(RuntimeError, match="simulated CONCURRENTLY failure"):
        await runner.apply()

    captured = capsys.readouterr()
    assert 'DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_t_x";' in captured.out

    # Migration NOT recorded.
    assert "INSERT INTO norm_migrations (name) VALUES ($1)" not in raw.executed
