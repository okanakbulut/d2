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
