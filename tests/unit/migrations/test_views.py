"""Unit tests for View migration operations + diff (issue 145)."""

from norm.migrations.operations import CreateView, DropView
from norm.migrations.state import SchemaState, ViewState


class TestCreateViewToDdl:
    def test_emits_create_or_replace_view_with_schema(self):
        op = CreateView(
            name="active_users",
            definition='SELECT "id","email" FROM "public"."users" WHERE "deleted_at" IS NULL',
            schema="public",
            replace=True,
        )
        expected = (
            'CREATE OR REPLACE VIEW "public"."active_users" AS '
            'SELECT "id","email" FROM "public"."users" WHERE "deleted_at" IS NULL'
        )
        assert op.to_ddl() == expected

    def test_emits_create_view_when_replace_false(self):
        op = CreateView(
            name="active_users",
            definition='SELECT "id" FROM "users"',
            schema="public",
            replace=False,
        )
        expected = (
            'CREATE VIEW "public"."active_users" AS '
            'SELECT "id" FROM "users"'
        )
        assert op.to_ddl() == expected

    def test_emits_create_view_without_schema(self):
        op = CreateView(
            name="v",
            definition='SELECT 1',
            schema=None,
            replace=True,
        )
        assert op.to_ddl() == 'CREATE OR REPLACE VIEW "v" AS SELECT 1'


class TestCreateViewApply:
    def test_stores_view_state_with_definition_and_columns(self):
        state = SchemaState()
        op = CreateView(
            name="active_users",
            definition='SELECT "id" FROM "users"',
            schema="public",
            columns=(("id", int),),
            replace=True,
        )
        op.apply(state)
        assert state.views == {
            "active_users": ViewState(
                definition='SELECT "id" FROM "users"',
                columns=(("id", int),),
                schema="public",
            )
        }


class TestDropViewToDdl:
    def test_emits_drop_view_if_exists_with_schema(self):
        op = DropView(name="active_users", schema="public")
        assert op.to_ddl() == 'DROP VIEW IF EXISTS "public"."active_users"'

    def test_emits_drop_view_with_cascade(self):
        op = DropView(name="v", schema="public", cascade=True)
        assert op.to_ddl() == 'DROP VIEW IF EXISTS "public"."v" CASCADE'

    def test_emits_drop_view_without_schema(self):
        op = DropView(name="v", schema=None)
        assert op.to_ddl() == 'DROP VIEW IF EXISTS "v"'


class TestDropViewApply:
    def test_removes_view_from_state(self):
        state = SchemaState()
        state.views["v"] = ViewState(
            definition="SELECT 1", columns=(("x", int),), schema="public",
        )
        DropView(name="v", schema="public").apply(state)
        assert state.views == {}
