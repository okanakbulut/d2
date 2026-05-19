"""Unit tests for RunSQL / RunPython escape hatches (issue 148)."""


from pathlib import Path
from typing import Any, ClassVar

import pytest

from norm.connection import AsyncConnection
from norm.migrations import Migration
from norm.migrations.operations import Operation, RunPython, RunSQL
from norm.migrations.runner import MigrationRunner
from norm.migrations.state import SchemaState


_CREATE_TRACKING_SQL = (
    "CREATE TABLE IF NOT EXISTS norm_migrations ("
    "id SERIAL PRIMARY KEY, "
    "name TEXT NOT NULL UNIQUE, "
    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")"
)


class _StubRaw:
    def __init__(self, applied: list[str] | None = None) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._applied = applied or []

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append((sql, args))

    async def fetch(self, sql: str, *args: object) -> list[dict[str, Any]]:
        return [{"name": n} for n in sorted(self._applied)]

    def transaction(self) -> "_StubRaw":
        return self

    async def __aenter__(self) -> "_StubRaw":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _StubConn(AsyncConnection):
    def __init__(self, raw: _StubRaw) -> None:  # noqa: D401 — intentional override
        # Skip AsyncConnection.__init__ to avoid pulling in dialect machinery;
        # tests only exercise the raw_* methods which read ``self._conn``.
        self._conn = raw


def _runner_with(
    raw: _StubRaw,
    migs: list[tuple[str, type[Migration]]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> MigrationRunner:
    runner = MigrationRunner(conn=_StubConn(raw), migrations_dir=str(tmp_path))
    monkeypatch.setattr(runner, "_discover", lambda: migs)
    return runner


class TestRunSQLApply:
    def test_apply_does_not_mutate_schema_state(self):
        state = SchemaState()
        op = RunSQL(sql="INSERT INTO foo (id) VALUES (1)")
        op.apply(state)
        assert state == SchemaState()

    def test_reverse_sql_defaults_to_none(self):
        op = RunSQL(sql="INSERT INTO foo (id) VALUES (1)")
        assert op.reverse_sql is None

    def test_reverse_sql_can_be_provided(self):
        op = RunSQL(
            sql="INSERT INTO foo (id) VALUES (1)",
            reverse_sql="DELETE FROM foo WHERE id = 1",
        )
        assert op.reverse_sql == "DELETE FROM foo WHERE id = 1"


class TestRunPythonApply:
    def test_apply_does_not_mutate_schema_state(self):
        async def _fn(conn: AsyncConnection) -> None:
            return None

        state = SchemaState()
        op = RunPython(fn=_fn)
        op.apply(state)
        assert state == SchemaState()

    def test_reverse_fn_defaults_to_none(self):
        async def _fn(conn: AsyncConnection) -> None:
            return None

        op = RunPython(fn=_fn)
        assert op.reverse_fn is None


class TestRunnerRunSQLDispatch:
    @pytest.mark.asyncio
    async def test_apply_splits_sql_on_semicolon_and_executes_each(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Mig(Migration):
            name = "0001_seed"
            operations = [
                RunSQL(
                    sql=(
                        "INSERT INTO foo (id) VALUES (1); "
                        "INSERT INTO foo (id) VALUES (2)"
                    )
                ),
            ]
            reverse_operations: ClassVar[list[Operation] | None] = []

        raw = _StubRaw()
        runner = _runner_with(raw, [("0001_seed", _Mig)], tmp_path, monkeypatch)

        await runner.apply()

        assert raw.executed == [
            (_CREATE_TRACKING_SQL, ()),
            (_CREATE_TRACKING_SQL, ()),
            ("INSERT INTO foo (id) VALUES (1)", ()),
            ("INSERT INTO foo (id) VALUES (2)", ()),
            ("INSERT INTO norm_migrations (name) VALUES ($1)", ("0001_seed",)),
        ]

    @pytest.mark.asyncio
    async def test_apply_ignores_empty_statements_from_trailing_semicolon(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Mig(Migration):
            name = "0001_seed"
            operations = [RunSQL(sql="INSERT INTO foo (id) VALUES (1);")]
            reverse_operations: ClassVar[list[Operation] | None] = []

        raw = _StubRaw()
        runner = _runner_with(raw, [("0001_seed", _Mig)], tmp_path, monkeypatch)

        await runner.apply()

        assert raw.executed == [
            (_CREATE_TRACKING_SQL, ()),
            (_CREATE_TRACKING_SQL, ()),
            ("INSERT INTO foo (id) VALUES (1)", ()),
            ("INSERT INTO norm_migrations (name) VALUES ($1)", ("0001_seed",)),
        ]


class TestRunnerRunPythonDispatch:
    @pytest.mark.asyncio
    async def test_apply_awaits_fn_with_async_connection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen_conns: list[object] = []

        async def _backfill(conn: AsyncConnection) -> None:
            seen_conns.append(conn)

        class _Mig(Migration):
            name = "0001_backfill"
            operations = [RunPython(fn=_backfill)]
            reverse_operations: ClassVar[list[Operation] | None] = []

        raw = _StubRaw()
        conn = _StubConn(raw)
        runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
        monkeypatch.setattr(runner, "_discover", lambda: [("0001_backfill", _Mig)])

        await runner.apply()

        assert seen_conns == [conn]
        assert raw.executed == [
            (_CREATE_TRACKING_SQL, ()),
            (_CREATE_TRACKING_SQL, ()),
            ("INSERT INTO norm_migrations (name) VALUES ($1)", ("0001_backfill",)),
        ]


class TestRollbackRunSQL:
    @pytest.mark.asyncio
    async def test_rollback_executes_reverse_sql_statements(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Mig(Migration):
            name = "0001_seed"
            operations = [
                RunSQL(
                    sql="INSERT INTO foo (id) VALUES (1)",
                    reverse_sql="DELETE FROM foo WHERE id = 1; DELETE FROM bar",
                ),
            ]
            reverse_operations = [
                RunSQL(
                    sql="INSERT INTO foo (id) VALUES (1)",
                    reverse_sql="DELETE FROM foo WHERE id = 1; DELETE FROM bar",
                ),
            ]

        raw = _StubRaw(applied=["0001_seed"])
        runner = _runner_with(raw, [("0001_seed", _Mig)], tmp_path, monkeypatch)

        await runner.rollback("0001_seed")

        assert raw.executed == [
            (_CREATE_TRACKING_SQL, ()),
            (_CREATE_TRACKING_SQL, ()),
            ("DELETE FROM foo WHERE id = 1", ()),
            ("DELETE FROM bar", ()),
            ("DELETE FROM norm_migrations WHERE name = $1", ("0001_seed",)),
        ]

    @pytest.mark.asyncio
    async def test_rollback_raises_when_reverse_sql_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Mig(Migration):
            name = "0001_seed"
            operations = [RunSQL(sql="INSERT INTO foo (id) VALUES (1)")]
            reverse_operations = [RunSQL(sql="INSERT INTO foo (id) VALUES (1)")]

        raw = _StubRaw(applied=["0001_seed"])
        runner = _runner_with(raw, [("0001_seed", _Mig)], tmp_path, monkeypatch)

        with pytest.raises(RuntimeError, match="0001_seed"):
            await runner.rollback("0001_seed")


class TestRollbackRunPython:
    @pytest.mark.asyncio
    async def test_rollback_awaits_reverse_fn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen_conns: list[object] = []

        async def _fwd(conn: AsyncConnection) -> None:
            return None

        async def _rev(conn: AsyncConnection) -> None:
            seen_conns.append(conn)

        class _Mig(Migration):
            name = "0001_backfill"
            operations = [RunPython(fn=_fwd, reverse_fn=_rev)]
            reverse_operations = [RunPython(fn=_fwd, reverse_fn=_rev)]

        raw = _StubRaw(applied=["0001_backfill"])
        conn = _StubConn(raw)
        runner = MigrationRunner(conn=conn, migrations_dir=str(tmp_path))
        monkeypatch.setattr(runner, "_discover", lambda: [("0001_backfill", _Mig)])

        await runner.rollback("0001_backfill")

        assert seen_conns == [conn]
        assert raw.executed == [
            (_CREATE_TRACKING_SQL, ()),
            (_CREATE_TRACKING_SQL, ()),
            ("DELETE FROM norm_migrations WHERE name = $1", ("0001_backfill",)),
        ]

    @pytest.mark.asyncio
    async def test_rollback_raises_when_reverse_fn_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fwd(conn: AsyncConnection) -> None:
            return None

        class _Mig(Migration):
            name = "0001_backfill"
            operations = [RunPython(fn=_fwd)]
            reverse_operations = [RunPython(fn=_fwd)]

        raw = _StubRaw(applied=["0001_backfill"])
        runner = _runner_with(raw, [("0001_backfill", _Mig)], tmp_path, monkeypatch)

        with pytest.raises(RuntimeError, match="0001_backfill"):
            await runner.rollback("0001_backfill")


class TestCheckDdlLint:
    def _setup(self, tmp_path: Path, mig_body: str) -> None:
        (tmp_path / "models.py").write_text("")
        (tmp_path / "pyproject.toml").write_text("[tool.norm]\n")
        migs = tmp_path / "migrations"
        migs.mkdir()
        (migs / "0001_seed.py").write_text(mig_body)

    def test_lint_flags_alter_in_run_sql(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys

        from norm.migrations.__main__ import cmd_check

        self._setup(
            tmp_path,
            (
                "from norm.migrations import Migration\n"
                "from norm.migrations.operations import RunSQL\n"
                "class Migration(Migration):\n"
                '    name = "0001_seed"\n'
                "    operations = [RunSQL(sql='ALTER TABLE foo ADD COLUMN x INT')]\n"
                "    reverse_operations: ClassVar[list[Operation] | None] = []\n"
            ),
        )

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_check(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc != 0
        out = capsys.readouterr().out
        assert str(tmp_path / "migrations" / "0001_seed.py") in out
        assert "ALTER" in out
        assert "RunSQL" in out

    def test_lint_allows_dml_in_run_sql(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import sys

        from norm.migrations.__main__ import cmd_check

        self._setup(
            tmp_path,
            (
                "from norm.migrations import Migration\n"
                "from norm.migrations.operations import RunSQL\n"
                "class Migration(Migration):\n"
                '    name = "0001_seed"\n'
                "    operations = [RunSQL(sql='INSERT INTO foo (id) VALUES (1)')]\n"
                "    reverse_operations: ClassVar[list[Operation] | None] = []\n"
            ),
        )

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_check(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_lint_flags_create_drop_truncate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import sys

        from norm.migrations.__main__ import cmd_check

        for kw in ("CREATE INDEX foo_x ON foo (x)", "DROP TABLE foo", "TRUNCATE foo"):
            # Fresh tmp dir per keyword via subfolder.
            sub = tmp_path / kw.split()[0].lower()
            sub.mkdir()
            self._setup(
                sub,
                (
                    "from norm.migrations import Migration\n"
                    "from norm.migrations.operations import RunSQL\n"
                    "class Migration(Migration):\n"
                    '    name = "0001_seed"\n'
                    f"    operations = [RunSQL(sql={kw!r})]\n"
                    "    reverse_operations: ClassVar[list[Operation] | None] = []\n"
                ),
            )
            sys.path.insert(0, str(sub))
            try:
                rc = cmd_check(cwd=sub)
            finally:
                sys.path.remove(str(sub))
            assert rc != 0, kw


class TestCodegenPreservesEscapeHatches:
    def test_make_after_run_sql_only_migration_detects_no_drift(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Replay must treat RunSQL as a no-op for state, so codegen sees no drift."""
        import sys

        from norm.migrations.__main__ import cmd_make

        (tmp_path / "models.py").write_text("")
        (tmp_path / "pyproject.toml").write_text("[tool.norm]\n")
        migs = tmp_path / "migrations"
        migs.mkdir()
        (migs / "0001_seed.py").write_text(
            "from norm.migrations import Migration\n"
            "from norm.migrations.operations import RunSQL\n"
            "class Migration(Migration):\n"
            '    name = "0001_seed"\n'
            "    operations = [RunSQL(sql='INSERT INTO foo (id) VALUES (1)')]\n"
            "    reverse_operations: ClassVar[list[Operation] | None] = []\n"
        )

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_make(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc == 0
        assert capsys.readouterr().out == "No changes detected.\n"
        # No new migration file was generated.
        assert sorted(p.name for p in migs.glob("*.py")) == ["0001_seed.py"]
