"""Unit tests for the Migration base class shape."""

from norm.migrations import Migration
from norm.migrations.operations import CreateTable, ColumnDef


class TestMigrationBase:
    def test_default_attributes(self):
        assert Migration.name == ""
        assert Migration.operations == []
        assert Migration.reverse_operations is None
        assert Migration.dependencies == []
        assert Migration.atomic is True

    def test_subclass_overrides(self):
        op = CreateTable(table="t", columns={"id": ColumnDef(type="BIGSERIAL")})

        class M(Migration):
            name = "0001_initial"
            operations = [op]
            dependencies = ["0000_base"]
            atomic = False

        assert M.name == "0001_initial"
        assert M.operations == [op]
        assert M.dependencies == ["0000_base"]
        assert M.atomic is False
        assert M.reverse_operations is None
