"""Unit tests for migration codegen."""

from pathlib import Path

from norm.migrations.codegen import make_migration
from norm.migrations.operations import (
    AddColumn,
    AlterColumnType,
    ColumnDef,
    CreateTable,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropTable,
    RenameColumn,
    SetColumnDefault,
    SetColumnNotNull,
)


EXPECTED_CREATE_SINGLE = '''from norm.migrations import Migration
from norm.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateIndex, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropIndex, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull


class Migration(Migration):
    name = "0001_create_users"
    dependencies = []
    operations = [
        CreateTable(
            table="users",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGSERIAL", nullable=False, default=None, primary_key=True),
                "email": ColumnDef(type="TEXT", nullable=False, default=None, primary_key=False),
            },
        ),
    ]
    reverse_operations = [
        DropTable(table="users", schema="public"),
    ]
'''


EXPECTED_AUTO_MULTI = '''from norm.migrations import Migration
from norm.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateIndex, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropIndex, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull


class Migration(Migration):
    name = "0002_auto"
    dependencies = ["0001_create_users"]
    operations = [
        CreateTable(
            table="a",
            schema=None,
            columns={
                "id": ColumnDef(type="BIGINT", nullable=False, default=None, primary_key=True),
            },
        ),
        CreateTable(
            table="b",
            schema=None,
            columns={
                "id": ColumnDef(type="BIGINT", nullable=False, default=None, primary_key=True),
            },
        ),
    ]
    reverse_operations = [
        DropTable(table="a", schema=None),
        DropTable(table="b", schema=None),
    ]
'''


class TestMakeMigration:
    def test_single_create_table_derives_label_and_writes_file(self, tmp_path: Path):
        forward = [
            CreateTable(
                table="users",
                schema="public",
                columns={
                    "id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True),
                    "email": ColumnDef(type="TEXT", nullable=False),
                },
            ),
        ]
        reverse = [DropTable(table="users", schema="public")]

        path = make_migration(
            migrations_dir=tmp_path,
            number=1,
            forward=forward,
            reverse=reverse,
            dependencies=[],
            label=None,
        )

        assert path.name == "0001_create_users.py"
        assert path.read_text() == EXPECTED_CREATE_SINGLE

    def test_single_drop_table_label(self, tmp_path: Path):
        forward = [DropTable(table="legacy", schema=None)]
        reverse = [
            CreateTable(
                table="legacy",
                schema=None,
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            )
        ]

        path = make_migration(
            migrations_dir=tmp_path,
            number=3,
            forward=forward,
            reverse=reverse,
            dependencies=["0002_x"],
            label=None,
        )
        assert path.name == "0003_drop_legacy.py"

    def test_multi_op_falls_back_to_auto_label(self, tmp_path: Path):
        forward = [
            CreateTable(
                table="a",
                schema=None,
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            ),
            CreateTable(
                table="b",
                schema=None,
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            ),
        ]
        reverse = [
            DropTable(table="a", schema=None),
            DropTable(table="b", schema=None),
        ]

        path = make_migration(
            migrations_dir=tmp_path,
            number=2,
            forward=forward,
            reverse=reverse,
            dependencies=["0001_create_users"],
            label=None,
        )
        assert path.name == "0002_auto.py"
        assert path.read_text() == EXPECTED_AUTO_MULTI

    def test_explicit_label_overrides_derivation(self, tmp_path: Path):
        forward = [
            CreateTable(
                table="t",
                schema=None,
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            ),
        ]
        reverse = [DropTable(table="t", schema=None)]

        path = make_migration(
            migrations_dir=tmp_path,
            number=4,
            forward=forward,
            reverse=reverse,
            dependencies=[],
            label="my_label",
        )
        assert path.name == "0004_my_label.py"


EXPECTED_COLUMN_OPS = '''from norm.migrations import Migration
from norm.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateIndex, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropIndex, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull


class Migration(Migration):
    name = "0005_auto"
    dependencies = ["0004_x"]
    operations = [
        AddColumn(table="t", column="email", type="TEXT", nullable=False, default="''", schema="public"),
        DropColumn(table="t", column="legacy", schema="public"),
        RenameColumn(table="t", old_name="a", new_name="b", schema="public"),
        AlterColumnType(table="t", column="x", type="BIGINT", schema="public"),
        SetColumnNotNull(table="t", column="x", schema="public"),
        DropColumnNotNull(table="t", column="y", schema="public"),
        SetColumnDefault(table="t", column="z", default="0", schema="public"),
        DropColumnDefault(table="t", column="w", schema="public"),
    ]
    reverse_operations = [
        DropColumn(table="t", column="email", schema="public"),
        AddColumn(table="t", column="legacy", type="TEXT", nullable=True, default=None, schema="public"),
        RenameColumn(table="t", old_name="b", new_name="a", schema="public"),
        AlterColumnType(table="t", column="x", type="INTEGER", schema="public"),
        DropColumnNotNull(table="t", column="x", schema="public"),
        SetColumnNotNull(table="t", column="y", schema="public"),
        DropColumnDefault(table="t", column="z", schema="public"),
        SetColumnDefault(table="t", column="w", default="'old'", schema="public"),
    ]
'''


class TestMakeMigrationColumnOps:
    def test_renders_all_column_ops(self, tmp_path: Path):
        forward = [
            AddColumn(table="t", column="email", type="TEXT", nullable=False, default="''", schema="public"),
            DropColumn(table="t", column="legacy", schema="public"),
            RenameColumn(table="t", old_name="a", new_name="b", schema="public"),
            AlterColumnType(table="t", column="x", type="BIGINT", schema="public"),
            SetColumnNotNull(table="t", column="x", schema="public"),
            DropColumnNotNull(table="t", column="y", schema="public"),
            SetColumnDefault(table="t", column="z", default="0", schema="public"),
            DropColumnDefault(table="t", column="w", schema="public"),
        ]
        reverse = [
            DropColumn(table="t", column="email", schema="public"),
            AddColumn(table="t", column="legacy", type="TEXT", nullable=True, default=None, schema="public"),
            RenameColumn(table="t", old_name="b", new_name="a", schema="public"),
            AlterColumnType(table="t", column="x", type="INTEGER", schema="public"),
            DropColumnNotNull(table="t", column="x", schema="public"),
            SetColumnNotNull(table="t", column="y", schema="public"),
            DropColumnDefault(table="t", column="z", schema="public"),
            SetColumnDefault(table="t", column="w", default="'old'", schema="public"),
        ]
        path = make_migration(
            migrations_dir=tmp_path,
            number=5,
            forward=forward,
            reverse=reverse,
            dependencies=["0004_x"],
            label=None,
        )
        assert path.name == "0005_auto.py"
        assert path.read_text() == EXPECTED_COLUMN_OPS
