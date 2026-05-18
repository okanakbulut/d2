"""Unit tests for migration codegen."""

from pathlib import Path

from norm.migrations.codegen import make_migration
from norm.migrations.operations import ColumnDef, CreateTable, DropTable


EXPECTED_CREATE_SINGLE = '''from norm.migrations import Migration
from norm.migrations.operations import ColumnDef, CreateTable, DropTable


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
from norm.migrations.operations import ColumnDef, CreateTable, DropTable


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
