"""Unit tests for foreign keys (issue 144)."""

from pathlib import Path

import pytest

from d2.migrations.snapshot import models_to_schema_state
from d2.migrations.state import ForeignKeyConstraint
from d2.model import field
from d2.schema import ForeignKey, PrimaryKey, Table
from d2 import db


class FkOrg(Table):
    id: PrimaryKey[int] = field(default=db.serial())


class FkUser(Table):
    id: PrimaryKey[int] = field(default=db.serial())
    org_id: ForeignKey[FkOrg] = field(on_delete=db.CASCADE)


class FkPost(Table):
    id: PrimaryKey[int] = field(default=db.serial())
    author_id: ForeignKey[FkUser] = field(on_delete=db.SET_NULL, on_update=db.CASCADE)


class FkAuthor(Table):
    id: PrimaryKey[int] = field(default=db.serial())
    org_id: ForeignKey[FkOrg] = field()


class TestSnapshotForeignKeys:
    def test_inline_fk_with_model_target_produces_constraint(self):
        state = models_to_schema_state([FkOrg, FkUser])
        assert state.tables["fk_users"].constraints == [
            ForeignKeyConstraint(
                name="fk_users_org_id_fkey",
                columns=("org_id",),
                references_schema="public",
                references_table="fk_orgs",
                references_column="id",
                on_delete="CASCADE",
                on_update=None,
            )
        ]

    def test_fk_with_on_delete_and_on_update(self):
        state = models_to_schema_state([FkOrg, FkUser, FkPost])
        assert state.tables["fk_posts"].constraints == [
            ForeignKeyConstraint(
                name="fk_posts_author_id_fkey",
                columns=("author_id",),
                references_schema="public",
                references_table="fk_users",
                references_column="id",
                on_delete="SET NULL",
                on_update="CASCADE",
            )
        ]

    def test_fk_without_on_delete_produces_constraint_with_no_action(self):
        state = models_to_schema_state([FkOrg, FkAuthor])
        assert state.tables["fk_authors"].constraints == [
            ForeignKeyConstraint(
                name="fk_authors_org_id_fkey",
                columns=("org_id",),
                references_schema="public",
                references_table="fk_orgs",
                references_column="id",
                on_delete=None,
                on_update=None,
            )
        ]


class TestAddConstraintForeignKeyDDL:
    def test_to_ddl_fk_with_on_delete_and_on_update(self):
        from d2.migrations.operations import AddConstraint

        op = AddConstraint(
            table="users",
            schema="public",
            constraint={
                "type": "foreign_key",
                "name": "users_org_id_fkey",
                "columns": ("org_id",),
                "references_schema": "public",
                "references_table": "organizations",
                "references_column": "id",
                "on_delete": "CASCADE",
                "on_update": "RESTRICT",
            },
        )
        expected = (
            'DO $$ BEGIN '
            'ALTER TABLE "public"."users" '
            'ADD CONSTRAINT "users_org_id_fkey" FOREIGN KEY ("org_id") '
            'REFERENCES "public"."organizations" ("id") '
            'ON DELETE CASCADE ON UPDATE RESTRICT; '
            'EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$'
        )
        assert op.to_ddl() == expected

    def test_to_ddl_fk_without_on_delete_or_on_update(self):
        from d2.migrations.operations import AddConstraint

        op = AddConstraint(
            table="users",
            constraint={
                "type": "foreign_key",
                "name": "users_org_id_fkey",
                "columns": ("org_id",),
                "references_schema": None,
                "references_table": "organizations",
                "references_column": "id",
                "on_delete": None,
                "on_update": None,
            },
        )
        expected = (
            'DO $$ BEGIN '
            'ALTER TABLE "users" '
            'ADD CONSTRAINT "users_org_id_fkey" FOREIGN KEY ("org_id") '
            'REFERENCES "organizations" ("id"); '
            'EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$'
        )
        assert op.to_ddl() == expected


EXPECTED_CODEGEN_FK = '''from d2.migrations import Migration
from d2.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateExtension, CreateIndex, CreateSchema, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropExtension, DropIndex, DropSchema, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull


class Migration(Migration):
    name = "0002_auto"
    dependencies = ["0001_init"]
    operations = [
        AddConstraint(table="users", constraint={"type": "foreign_key", "name": "users_org_id_fkey", "columns": ("org_id",), "references_schema": "public", "references_table": "orgs", "references_column": "id", "on_delete": "CASCADE", "on_update": None}, schema="public"),
    ]
    reverse_operations = [
        DropConstraint(table="users", name="users_org_id_fkey", schema="public"),
    ]
'''


class TestCodegenForeignKey:
    def test_renders_foreign_key_constraint_dict_with_all_fields(self, tmp_path: Path) -> None:
        from d2.migrations.codegen import make_migration
        from d2.migrations.operations import AddConstraint, DropConstraint, Operation

        forward: list[Operation] = [
            AddConstraint(
                table="users",
                constraint={
                    "type": "foreign_key",
                    "name": "users_org_id_fkey",
                    "columns": ("org_id",),
                    "references_schema": "public",
                    "references_table": "orgs",
                    "references_column": "id",
                    "on_delete": "CASCADE",
                    "on_update": None,
                },
                schema="public",
            ),
        ]
        reverse: list[Operation] = [
            DropConstraint(table="users", name="users_org_id_fkey", schema="public"),
        ]
        path = make_migration(
            migrations_dir=tmp_path,
            number=2,
            forward=forward,
            reverse=reverse,
            dependencies=["0001_init"],
            label=None,
        )
        assert path.read_text() == EXPECTED_CODEGEN_FK


class TestForeignKeyAutoNameTooLong:
    def test_auto_fk_name_too_long_raises_pointing_at_name_kwarg(self):
        from d2.migrations.naming import (
            IdentifierTooLongError,
            auto_fk_name,
        )

        long_table = "t" * 55
        with pytest.raises(IdentifierTooLongError) as exc:
            auto_fk_name(long_table, ("col_one", "col_two"))
        assert "name=" in str(exc.value)


class TestDiffForeignKeyDeferredOrdering:
    def test_fk_add_constraints_emitted_after_all_create_tables(self):
        from d2.migrations.draft import diff_states
        from d2.migrations.operations import (
            AddConstraint,
            ColumnDef,
            CreateTable,
            DropTable,
        )
        from d2.migrations.state import (
            ColumnState,
            ForeignKeyConstraint,
            SchemaState,
            TableState,
        )

        current = SchemaState()
        target = SchemaState()
        target.tables["fk_org"] = TableState(
            columns={"id": ColumnState(type="BIGINT", nullable=False, primary_key=True)},
            schema="public",
        )
        fk = ForeignKeyConstraint(
            name="fk_user_org_id_fkey",
            columns=("org_id",),
            references_schema="public",
            references_table="fk_org",
            references_column="id",
            on_delete="CASCADE",
            on_update=None,
        )
        target.tables["fk_user"] = TableState(
            columns={
                "id": ColumnState(type="BIGINT", nullable=False, primary_key=True),
                "org_id": ColumnState(type="BIGINT", nullable=False),
            },
            schema="public",
            constraints=[fk],
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateTable(
                table="fk_org",
                columns={
                    "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                },
                schema="public",
            ),
            CreateTable(
                table="fk_user",
                columns={
                    "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                    "org_id": ColumnDef(type="BIGINT", nullable=False),
                },
                schema="public",
            ),
            AddConstraint(table="fk_user", constraint=fk, schema="public"),
        ]
        assert reverse == [
            DropTable(table="fk_org", schema="public"),
            DropTable(table="fk_user", schema="public"),
        ]

    def test_fk_add_constraints_deferred_when_multiple_tables_have_fks(self):
        """If two new tables both have FKs, ALL CreateTables come first, THEN all FKs."""
        from d2.migrations.draft import diff_states
        from d2.migrations.operations import (
            AddConstraint,
            ColumnDef,
            CreateTable,
            DropTable,
        )
        from d2.migrations.state import (
            ColumnState,
            ForeignKeyConstraint,
            SchemaState,
            TableState,
            UniqueConstraint,
        )

        current = SchemaState()
        target = SchemaState()
        unique = UniqueConstraint(name="a_tbl_x_key", columns=("x",))
        fk_a = ForeignKeyConstraint(
            name="a_tbl_y_fkey",
            columns=("y",),
            references_schema="public",
            references_table="z_tbl",
            references_column="id",
            on_delete=None,
            on_update=None,
        )
        target.tables["a_tbl"] = TableState(
            columns={
                "x": ColumnState(type="TEXT", nullable=False),
                "y": ColumnState(type="BIGINT", nullable=False),
            },
            schema="public",
            constraints=[unique, fk_a],
        )
        target.tables["z_tbl"] = TableState(
            columns={"id": ColumnState(type="BIGINT", nullable=False, primary_key=True)},
            schema="public",
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateTable(
                table="a_tbl",
                columns={
                    "x": ColumnDef(type="TEXT", nullable=False),
                    "y": ColumnDef(type="BIGINT", nullable=False),
                },
                schema="public",
            ),
            AddConstraint(table="a_tbl", constraint=unique, schema="public"),
            CreateTable(
                table="z_tbl",
                columns={
                    "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                },
                schema="public",
            ),
            AddConstraint(table="a_tbl", constraint=fk_a, schema="public"),
        ]
        assert reverse == [
            DropTable(table="a_tbl", schema="public"),
            DropTable(table="z_tbl", schema="public"),
        ]

    def test_new_fk_on_existing_table_yields_add_and_reverse_drop(self):
        from d2.migrations.draft import diff_states
        from d2.migrations.operations import AddConstraint, DropConstraint
        from d2.migrations.state import (
            ColumnState,
            ForeignKeyConstraint,
            SchemaState,
            TableState,
        )

        fk = ForeignKeyConstraint(
            name="u_org_id_fkey",
            columns=("org_id",),
            references_schema="public",
            references_table="orgs",
            references_column="id",
            on_delete="CASCADE",
            on_update=None,
        )
        current = SchemaState()
        current.tables["u"] = TableState(
            columns={"org_id": ColumnState(type="BIGINT", nullable=False)},
            schema="public",
        )
        target = SchemaState()
        target.tables["u"] = TableState(
            columns={"org_id": ColumnState(type="BIGINT", nullable=False)},
            schema="public",
            constraints=[fk],
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            AddConstraint(table="u", constraint=fk, schema="public"),
        ]
        assert reverse == [
            DropConstraint(table="u", name="u_org_id_fkey", schema="public"),
        ]
