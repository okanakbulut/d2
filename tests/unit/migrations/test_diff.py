"""Unit tests for diff_states and DropTable op."""

from norm.migrations.draft import diff_states
from norm.migrations.operations import ColumnDef, CreateTable, DropTable
from norm.migrations.state import SchemaState


class TestDropTable:
    def test_to_ddl_with_schema(self):
        assert (
            DropTable(table="users", schema="public").to_ddl()
            == 'DROP TABLE IF EXISTS "public"."users"'
        )

    def test_to_ddl_without_schema(self):
        assert DropTable(table="t").to_ddl() == 'DROP TABLE IF EXISTS "t"'

    def test_apply_removes_table(self):
        state = SchemaState()
        CreateTable(table="t", columns={"id": ColumnDef(type="BIGINT")}).apply(state)
        DropTable(table="t").apply(state)
        assert state.tables == {}


class TestDiffStates:
    def test_empty_states_yield_no_ops(self):
        assert diff_states(SchemaState(), SchemaState()) == ([], [])

    def test_new_table_in_target_yields_create_and_reverse_drop(self):
        current = SchemaState()
        target = SchemaState()
        op = CreateTable(
            table="users",
            schema="public",
            columns={"id": ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True)},
        )
        op.apply(target)

        forward, reverse = diff_states(current, target)

        assert forward == [
            CreateTable(
                table="users",
                schema="public",
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            )
        ]
        assert reverse == [DropTable(table="users", schema="public")]

    def test_table_dropped_from_current_yields_drop_and_reverse_create(self):
        current = SchemaState()
        target = SchemaState()
        CreateTable(
            table="orders",
            schema=None,
            columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
        ).apply(current)

        forward, reverse = diff_states(current, target)

        assert forward == [DropTable(table="orders", schema=None)]
        assert reverse == [
            CreateTable(
                table="orders",
                schema=None,
                columns={"id": ColumnDef(type="BIGINT", nullable=False, primary_key=True)},
            )
        ]
