"""Unit tests for migration operations (issue 140 tracer slice)."""

import pytest

from norm.migrations.operations import (
    AddColumn,
    AlterColumnType,
    ColumnDef,
    CreateExtension,
    CreateSchema,
    CreateTable,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropExtension,
    DropSchema,
    RenameColumn,
    SetColumnDefault,
    SetColumnNotNull,
)
from norm.migrations.state import ColumnState, SchemaError, SchemaState, TableState


class TestCreateTableToDdl:
    def test_emits_create_table_if_not_exists_with_schema(self):
        op = CreateTable(
            table="users",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True),
                "email": ColumnDef(type="TEXT", nullable=False),
            },
        )
        expected = (
            'CREATE TABLE IF NOT EXISTS "public"."users" '
            '("id" BIGSERIAL NOT NULL PRIMARY KEY, '
            '"email" TEXT NOT NULL)'
        )
        assert op.to_ddl() == expected


class TestCreateTableApply:
    def test_normalizes_bigserial_to_bigint_with_sequence_default_flag(self):
        op = CreateTable(
            table="users",
            schema="public",
            columns={
                "id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True),
                "email": ColumnDef(type="TEXT", nullable=False),
            },
        )
        state = SchemaState()
        op.apply(state)

        assert set(state.tables.keys()) == {"users"}
        table = state.tables["users"]
        assert table.schema == "public"
        assert list(table.columns.keys()) == ["id", "email"]

        id_col = table.columns["id"]
        assert id_col.type == "BIGINT"
        assert id_col.nullable is False
        assert id_col.primary_key is True
        assert id_col.has_sequence_default is True
        assert id_col.default is None

        email_col = table.columns["email"]
        assert email_col.type == "TEXT"
        assert email_col.nullable is False
        assert email_col.has_sequence_default is False

    def test_normalizes_serial_and_smallserial(self):
        op = CreateTable(
            table="t",
            schema=None,
            columns={
                "a": ColumnDef(type="SERIAL", nullable=False),
                "b": ColumnDef(type="SMALLSERIAL", nullable=False),
            },
        )
        state = SchemaState()
        op.apply(state)
        assert state.tables["t"].columns["a"].type == "INTEGER"
        assert state.tables["t"].columns["a"].has_sequence_default is True
        assert state.tables["t"].columns["b"].type == "SMALLINT"
        assert state.tables["t"].columns["b"].has_sequence_default is True


def _make_state_with_table(columns: dict[str, ColumnState]) -> SchemaState:
    state = SchemaState()
    state.tables["t"] = TableState(columns=dict(columns), schema="public")
    return state


class TestAddColumn:
    def test_to_ddl_nullable_no_default(self):
        op = AddColumn(table="t", column="age", type="INTEGER", nullable=True, schema="public")
        assert op.to_ddl() == 'ALTER TABLE "public"."t" ADD COLUMN "age" INTEGER'

    def test_to_ddl_not_null_with_default(self):
        op = AddColumn(
            table="t",
            column="status",
            type="TEXT",
            nullable=False,
            default="'active'",
            schema="public",
        )
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ADD COLUMN "status" TEXT NOT NULL DEFAULT \'active\''
        )

    def test_to_ddl_no_schema(self):
        op = AddColumn(table="t", column="x", type="TEXT", nullable=True)
        assert op.to_ddl() == 'ALTER TABLE "t" ADD COLUMN "x" TEXT'

    def test_apply_adds_column_to_state(self):
        state = _make_state_with_table({"id": ColumnState(type="BIGINT", nullable=False)})
        AddColumn(
            table="t",
            column="email",
            type="TEXT",
            nullable=False,
            default="''",
            schema="public",
        ).apply(state)
        col = state.tables["t"].columns["email"]
        assert col == ColumnState(
            type="TEXT", nullable=False, default="''", primary_key=False,
        )

    def test_apply_raises_when_table_missing(self):
        with pytest.raises(SchemaError):
            AddColumn(table="missing", column="x", type="TEXT", nullable=True).apply(SchemaState())

    def test_apply_raises_when_column_exists(self):
        state = _make_state_with_table({"x": ColumnState(type="TEXT", nullable=True)})
        with pytest.raises(SchemaError):
            AddColumn(table="t", column="x", type="TEXT", nullable=True, schema="public").apply(state)


class TestDropColumn:
    def test_to_ddl_with_schema(self):
        assert (
            DropColumn(table="t", column="x", schema="public").to_ddl()
            == 'ALTER TABLE "public"."t" DROP COLUMN "x"'
        )

    def test_to_ddl_without_schema(self):
        assert DropColumn(table="t", column="x").to_ddl() == 'ALTER TABLE "t" DROP COLUMN "x"'

    def test_apply_removes_column(self):
        state = _make_state_with_table({
            "id": ColumnState(type="BIGINT", nullable=False),
            "x": ColumnState(type="TEXT", nullable=True),
        })
        DropColumn(table="t", column="x", schema="public").apply(state)
        assert list(state.tables["t"].columns.keys()) == ["id"]

    def test_apply_raises_when_column_missing(self):
        state = _make_state_with_table({"id": ColumnState(type="BIGINT", nullable=False)})
        with pytest.raises(SchemaError):
            DropColumn(table="t", column="nope", schema="public").apply(state)


class TestRenameColumn:
    def test_to_ddl_with_schema(self):
        assert (
            RenameColumn(table="t", old_name="a", new_name="b", schema="public").to_ddl()
            == 'ALTER TABLE "public"."t" RENAME COLUMN "a" TO "b"'
        )

    def test_to_ddl_without_schema(self):
        assert (
            RenameColumn(table="t", old_name="a", new_name="b").to_ddl()
            == 'ALTER TABLE "t" RENAME COLUMN "a" TO "b"'
        )

    def test_apply_renames_preserving_order_and_state(self):
        state = _make_state_with_table({
            "id": ColumnState(type="BIGINT", nullable=False),
            "old_name": ColumnState(type="TEXT", nullable=True, default="'x'"),
            "z": ColumnState(type="INTEGER", nullable=True),
        })
        RenameColumn(table="t", old_name="old_name", new_name="new_name", schema="public").apply(state)
        cols = state.tables["t"].columns
        assert list(cols.keys()) == ["id", "new_name", "z"]
        assert cols["new_name"] == ColumnState(type="TEXT", nullable=True, default="'x'")

    def test_apply_raises_when_old_missing(self):
        state = _make_state_with_table({"id": ColumnState(type="BIGINT", nullable=False)})
        with pytest.raises(SchemaError):
            RenameColumn(table="t", old_name="nope", new_name="x", schema="public").apply(state)

    def test_apply_raises_when_new_name_exists(self):
        state = _make_state_with_table({
            "a": ColumnState(type="TEXT", nullable=True),
            "b": ColumnState(type="TEXT", nullable=True),
        })
        with pytest.raises(SchemaError):
            RenameColumn(table="t", old_name="a", new_name="b", schema="public").apply(state)


class TestAlterColumnType:
    def test_to_ddl(self):
        op = AlterColumnType(table="t", column="x", type="BIGINT", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ALTER COLUMN "x" TYPE BIGINT'
        )

    def test_to_ddl_no_schema(self):
        op = AlterColumnType(table="t", column="x", type="TEXT")
        assert op.to_ddl() == 'ALTER TABLE "t" ALTER COLUMN "x" TYPE TEXT'

    def test_apply_mutates_type_only(self):
        state = _make_state_with_table({
            "x": ColumnState(type="INTEGER", nullable=False, default="0"),
        })
        AlterColumnType(table="t", column="x", type="BIGINT", schema="public").apply(state)
        assert state.tables["t"].columns["x"] == ColumnState(
            type="BIGINT", nullable=False, default="0",
        )


class TestSetColumnNotNull:
    def test_to_ddl(self):
        op = SetColumnNotNull(table="t", column="x", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ALTER COLUMN "x" SET NOT NULL'
        )

    def test_apply(self):
        state = _make_state_with_table({"x": ColumnState(type="TEXT", nullable=True)})
        SetColumnNotNull(table="t", column="x", schema="public").apply(state)
        assert state.tables["t"].columns["x"].nullable is False


class TestDropColumnNotNull:
    def test_to_ddl(self):
        op = DropColumnNotNull(table="t", column="x", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ALTER COLUMN "x" DROP NOT NULL'
        )

    def test_apply(self):
        state = _make_state_with_table({"x": ColumnState(type="TEXT", nullable=False)})
        DropColumnNotNull(table="t", column="x", schema="public").apply(state)
        assert state.tables["t"].columns["x"].nullable is True


class TestSetColumnDefault:
    def test_to_ddl(self):
        op = SetColumnDefault(table="t", column="x", default="'hi'", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ALTER COLUMN "x" SET DEFAULT \'hi\''
        )

    def test_apply(self):
        state = _make_state_with_table({"x": ColumnState(type="TEXT", nullable=True)})
        SetColumnDefault(table="t", column="x", default="'hi'", schema="public").apply(state)
        assert state.tables["t"].columns["x"].default == "'hi'"


class TestDropColumnDefault:
    def test_to_ddl(self):
        op = DropColumnDefault(table="t", column="x", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."t" ALTER COLUMN "x" DROP DEFAULT'
        )

    def test_apply(self):
        state = _make_state_with_table({"x": ColumnState(type="TEXT", nullable=True, default="'hi'")})
        DropColumnDefault(table="t", column="x", schema="public").apply(state)
        assert state.tables["t"].columns["x"].default is None


class TestCreateExtension:
    def test_to_ddl(self):
        assert (
            CreateExtension(name="pgcrypto").to_ddl()
            == 'CREATE EXTENSION IF NOT EXISTS "pgcrypto"'
        )

    def test_apply_adds_to_state(self):
        state = SchemaState()
        CreateExtension(name="pgcrypto").apply(state)
        assert state.extensions == {"pgcrypto"}


class TestDropExtension:
    def test_to_ddl(self):
        assert (
            DropExtension(name="pgcrypto").to_ddl()
            == 'DROP EXTENSION IF EXISTS "pgcrypto"'
        )

    def test_apply_removes_from_state(self):
        state = SchemaState(extensions={"pgcrypto", "uuid-ossp"})
        DropExtension(name="pgcrypto").apply(state)
        assert state.extensions == {"uuid-ossp"}


class TestCreateSchema:
    def test_to_ddl(self):
        assert (
            CreateSchema(name="audit").to_ddl()
            == 'CREATE SCHEMA IF NOT EXISTS "audit"'
        )

    def test_apply_adds_to_state(self):
        state = SchemaState()
        CreateSchema(name="audit").apply(state)
        assert state.schemas == {"audit"}


class TestDropSchema:
    def test_to_ddl_default(self):
        assert (
            DropSchema(name="audit").to_ddl()
            == 'DROP SCHEMA IF EXISTS "audit"'
        )

    def test_to_ddl_cascade(self):
        assert (
            DropSchema(name="audit", cascade=True).to_ddl()
            == 'DROP SCHEMA IF EXISTS "audit" CASCADE'
        )

    def test_apply_removes_from_state(self):
        state = SchemaState(schemas={"audit", "reporting"})
        DropSchema(name="audit").apply(state)
        assert state.schemas == {"reporting"}
