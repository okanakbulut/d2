"""Unit tests for MigrationRunner.rollback (issue 147)."""

from __future__ import annotations

from pathlib import Path

import pytest

from norm.migrations import Migration
from norm.migrations.operations import CreateTable, ColumnDef, DropTable
from norm.migrations.runner import MigrationRunner


_CREATE_TRACKING_SQL = (
    "CREATE TABLE IF NOT EXISTS norm_migrations ("
    "id SERIAL PRIMARY KEY, "
    "name TEXT NOT NULL UNIQUE, "
    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")"
)


class _StubRaw:
    def __init__(self, applied: list[str] | None = None) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._applied = applied or []
        self.txn_entered = 0

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append((sql, args))

    async def fetch(self, sql: str, *args: object) -> list:
        # Mimic `SELECT name FROM norm_migrations ORDER BY name`.
        return [{"name": n} for n in sorted(self._applied)]

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


class _MigA(Migration):
    name = "0001_a"
    operations = [
        CreateTable(
            table="a",
            schema=None,
            columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
        ),
    ]
    reverse_operations = [DropTable(table="a", schema=None)]


class _MigB(Migration):
    name = "0002_b"
    operations = [
        CreateTable(
            table="b",
            schema=None,
            columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
        ),
    ]
    reverse_operations = [DropTable(table="b", schema=None)]


def _runner_with(raw: _StubRaw, migs, tmp_path: Path, monkeypatch) -> MigrationRunner:
    runner = MigrationRunner(conn=_StubConn(raw), migrations_dir=str(tmp_path))
    monkeypatch.setattr(runner, "_discover", lambda: migs)
    return runner


@pytest.mark.asyncio
async def test_rollback_refuses_non_most_recent_without_force(
    tmp_path: Path, monkeypatch
) -> None:
    raw = _StubRaw(applied=["0001_a", "0002_b"])
    runner = _runner_with(
        raw, [("0001_a", _MigA), ("0002_b", _MigB)], tmp_path, monkeypatch
    )

    with pytest.raises(RuntimeError, match="not the most recently applied"):
        await runner.rollback("0001_a")

    # No DDL or delete was executed; only the tracking-table CREATE
    # (idempotent; called by rollback and again by applied()).
    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
    ]


class _MigNoReverse(Migration):
    name = "0001_no_reverse"
    operations = [
        CreateTable(
            table="z",
            schema=None,
            columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
        ),
    ]
    reverse_operations = None


@pytest.mark.asyncio
async def test_rollback_refuses_when_reverse_operations_is_none(
    tmp_path: Path, monkeypatch
) -> None:
    raw = _StubRaw(applied=["0001_no_reverse"])
    runner = _runner_with(
        raw, [("0001_no_reverse", _MigNoReverse)], tmp_path, monkeypatch
    )

    with pytest.raises(RuntimeError, match="reverse_operations = None"):
        await runner.rollback("0001_no_reverse")

    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
    ]


@pytest.mark.asyncio
async def test_rollback_empty_reverse_is_noop_but_removes_tracking_row(
    tmp_path: Path, monkeypatch
) -> None:
    class _Mig(Migration):
        name = "0001_empty"
        operations: list = []
        reverse_operations: list = []

    raw = _StubRaw(applied=["0001_empty"])
    runner = _runner_with(raw, [("0001_empty", _Mig)], tmp_path, monkeypatch)

    await runner.rollback("0001_empty")

    assert raw.txn_entered == 1
    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
        ("DELETE FROM norm_migrations WHERE name = $1", ("0001_empty",)),
    ]


@pytest.mark.asyncio
async def test_rollback_executes_reverse_ops_in_order_and_removes_tracking_row(
    tmp_path: Path, monkeypatch
) -> None:
    raw = _StubRaw(applied=["0001_a", "0002_b"])
    runner = _runner_with(
        raw, [("0001_a", _MigA), ("0002_b", _MigB)], tmp_path, monkeypatch
    )

    await runner.rollback("0002_b")

    assert raw.txn_entered == 1
    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
        ('DROP TABLE IF EXISTS "b"', ()),
        ("DELETE FROM norm_migrations WHERE name = $1", ("0002_b",)),
    ]


@pytest.mark.asyncio
async def test_rollback_with_force_allows_non_most_recent(
    tmp_path: Path, monkeypatch
) -> None:
    raw = _StubRaw(applied=["0001_a", "0002_b"])
    runner = _runner_with(
        raw, [("0001_a", _MigA), ("0002_b", _MigB)], tmp_path, monkeypatch
    )

    await runner.rollback("0001_a", force=True)

    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
        ('DROP TABLE IF EXISTS "a"', ()),
        ("DELETE FROM norm_migrations WHERE name = $1", ("0001_a",)),
    ]


@pytest.mark.asyncio
async def test_rollback_non_atomic_migration_skips_transaction(
    tmp_path: Path, monkeypatch
) -> None:
    from norm.migrations.operations import DropIndex

    class _NonAtomic(Migration):
        name = "0001_idx"
        atomic = False
        operations: list = []
        reverse_operations = [
            DropIndex(name="idx_x", concurrent=True, schema=None, table="t"),
        ]

    raw = _StubRaw(applied=["0001_idx"])
    runner = _runner_with(raw, [("0001_idx", _NonAtomic)], tmp_path, monkeypatch)

    await runner.rollback("0001_idx")

    assert raw.txn_entered == 0
    assert raw.executed == [
        (_CREATE_TRACKING_SQL, ()),
        (_CREATE_TRACKING_SQL, ()),
        ('DROP INDEX CONCURRENTLY IF EXISTS "idx_x"', ()),
        ("DELETE FROM norm_migrations WHERE name = $1", ("0001_idx",)),
    ]
