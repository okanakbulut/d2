"""Unit tests for migration operations (issue 140 tracer slice)."""

from norm.migrations.operations import CreateTable, ColumnDef
from norm.migrations.state import SchemaState


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
        assert id_col._has_sequence_default is True
        assert id_col.default is None

        email_col = table.columns["email"]
        assert email_col.type == "TEXT"
        assert email_col.nullable is False
        assert email_col._has_sequence_default is False

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
        assert state.tables["t"].columns["a"]._has_sequence_default is True
        assert state.tables["t"].columns["b"].type == "SMALLINT"
        assert state.tables["t"].columns["b"]._has_sequence_default is True
