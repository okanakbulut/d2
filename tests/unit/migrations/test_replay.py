"""Unit tests for migration file loading."""

from pathlib import Path

import pytest

from norm.migrations import Migration
from norm.migrations.replay import _load_migration


MIGRATION_SOURCE = '''
from norm.migrations import Migration
from norm.migrations.operations import CreateTable, ColumnDef


class Migration(Migration):
    name = "0001_initial"
    operations = [
        CreateTable(
            table="users",
            schema="public",
            columns={"id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True)},
        ),
    ]
'''


class TestLoadMigration:
    def test_returns_migration_subclass_from_file(self, tmp_path: Path):
        path = tmp_path / "0001_initial.py"
        path.write_text(MIGRATION_SOURCE)

        cls = _load_migration(path)

        assert issubclass(cls, Migration)
        assert cls.name == "0001_initial"
        assert len(cls.operations) == 1

    def test_raises_when_file_has_no_migration_subclass(self, tmp_path: Path):
        path = tmp_path / "0002_empty.py"
        path.write_text("x = 1\n")
        with pytest.raises(Exception):
            _load_migration(path)


REPLAY_0001 = '''
from norm.migrations import Migration
from norm.migrations.operations import CreateTable, ColumnDef


class Migration(Migration):
    name = "0001_initial"
    operations = [
        CreateTable(
            table="replay_users",
            schema=None,
            columns={"id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True)},
        ),
    ]
'''

REPLAY_0002 = '''
from norm.migrations import Migration
from norm.migrations.operations import DropTable


class Migration(Migration):
    name = "0002_drop"
    operations = [DropTable(table="replay_users")]
'''


class TestReplayMigrations:
    def test_reduces_files_in_sorted_order(self, tmp_path: Path):
        from norm.migrations.replay import replay_migrations

        (tmp_path / "0001_initial.py").write_text(REPLAY_0001)
        (tmp_path / "0002_drop.py").write_text(REPLAY_0002)

        state = replay_migrations(sorted(tmp_path.glob("*.py")))
        assert state.tables == {}

    def test_state_reflects_partial_replay(self, tmp_path: Path):
        from norm.migrations.replay import replay_migrations

        (tmp_path / "0001_initial.py").write_text(REPLAY_0001)
        state = replay_migrations(sorted(tmp_path.glob("*.py")))
        assert list(state.tables.keys()) == ["replay_users"]
