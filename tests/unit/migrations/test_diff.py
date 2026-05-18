"""Unit tests for diff_states and DropTable op."""

from norm.migrations.draft import diff_states
from norm.migrations.operations import (
    AddColumn,
    AddConstraint,
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
    DropTable,
    SetColumnDefault,
    SetColumnNotNull,
)
from norm.migrations.state import ColumnState, SchemaState, TableState


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


def _state_with(table_name: str, columns: dict, schema: str | None = "public") -> SchemaState:
    state = SchemaState()
    state.tables[table_name] = TableState(columns=dict(columns), schema=schema)
    return state


class TestDiffColumns:
    def test_new_column_in_target_yields_add_and_reverse_drop(self):
        current = _state_with("t", {"id": ColumnState(type="BIGINT", nullable=False)})
        target = _state_with("t", {
            "id": ColumnState(type="BIGINT", nullable=False),
            "email": ColumnState(type="TEXT", nullable=False, default="''"),
        })

        forward, reverse = diff_states(current, target)
        assert forward == [
            AddColumn(
                table="t",
                column="email",
                type="TEXT",
                nullable=False,
                default="''",
                schema="public",
            )
        ]
        assert reverse == [DropColumn(table="t", column="email", schema="public")]

    def test_dropped_column_yields_drop_and_reverse_add_from_current(self):
        current = _state_with("t", {
            "id": ColumnState(type="BIGINT", nullable=False),
            "legacy": ColumnState(type="TEXT", nullable=True, default="'old'"),
        })
        target = _state_with("t", {"id": ColumnState(type="BIGINT", nullable=False)})

        forward, reverse = diff_states(current, target)
        assert forward == [DropColumn(table="t", column="legacy", schema="public")]
        assert reverse == [
            AddColumn(
                table="t",
                column="legacy",
                type="TEXT",
                nullable=True,
                default="'old'",
                schema="public",
            )
        ]

    def test_type_only_change_emits_only_alter_type(self):
        current = _state_with("t", {"x": ColumnState(type="INTEGER", nullable=False, default="0")})
        target = _state_with("t", {"x": ColumnState(type="BIGINT", nullable=False, default="0")})

        forward, reverse = diff_states(current, target)
        assert forward == [AlterColumnType(table="t", column="x", type="BIGINT", schema="public")]
        assert reverse == [AlterColumnType(table="t", column="x", type="INTEGER", schema="public")]

    def test_nullable_true_to_false_emits_set_not_null(self):
        current = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True)})
        target = _state_with("t", {"x": ColumnState(type="TEXT", nullable=False)})

        forward, reverse = diff_states(current, target)
        assert forward == [SetColumnNotNull(table="t", column="x", schema="public")]
        assert reverse == [DropColumnNotNull(table="t", column="x", schema="public")]

    def test_nullable_false_to_true_emits_drop_not_null(self):
        current = _state_with("t", {"x": ColumnState(type="TEXT", nullable=False)})
        target = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True)})

        forward, reverse = diff_states(current, target)
        assert forward == [DropColumnNotNull(table="t", column="x", schema="public")]
        assert reverse == [SetColumnNotNull(table="t", column="x", schema="public")]

    def test_default_added_emits_set_default(self):
        current = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default=None)})
        target = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default="'hi'")})

        forward, reverse = diff_states(current, target)
        assert forward == [SetColumnDefault(table="t", column="x", default="'hi'", schema="public")]
        assert reverse == [DropColumnDefault(table="t", column="x", schema="public")]

    def test_default_dropped_emits_drop_default_and_reverse_set(self):
        current = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default="'old'")})
        target = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default=None)})

        forward, reverse = diff_states(current, target)
        assert forward == [DropColumnDefault(table="t", column="x", schema="public")]
        assert reverse == [SetColumnDefault(table="t", column="x", default="'old'", schema="public")]

    def test_default_changed_emits_set_default_with_reverse_set(self):
        current = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default="'old'")})
        target = _state_with("t", {"x": ColumnState(type="TEXT", nullable=True, default="'new'")})

        forward, reverse = diff_states(current, target)
        assert forward == [SetColumnDefault(table="t", column="x", default="'new'", schema="public")]
        assert reverse == [SetColumnDefault(table="t", column="x", default="'old'", schema="public")]

    def test_multi_field_change_emits_all_three_granular_ops(self):
        current = _state_with("t", {
            "x": ColumnState(type="INTEGER", nullable=True, default=None),
        })
        target = _state_with("t", {
            "x": ColumnState(type="BIGINT", nullable=False, default="0"),
        })

        forward, reverse = diff_states(current, target)
        assert forward == [
            AlterColumnType(table="t", column="x", type="BIGINT", schema="public"),
            SetColumnNotNull(table="t", column="x", schema="public"),
            SetColumnDefault(table="t", column="x", default="0", schema="public"),
        ]
        assert reverse == [
            AlterColumnType(table="t", column="x", type="INTEGER", schema="public"),
            DropColumnNotNull(table="t", column="x", schema="public"),
            DropColumnDefault(table="t", column="x", schema="public"),
        ]

    def test_unchanged_column_emits_nothing(self):
        cols = {"id": ColumnState(type="BIGINT", nullable=False)}
        forward, reverse = diff_states(_state_with("t", cols), _state_with("t", cols))
        assert forward == []
        assert reverse == []

    def test_rename_is_not_auto_detected(self):
        # A renamed column manifests as drop + add by diff (user must hand-edit).
        current = _state_with("t", {
            "id": ColumnState(type="BIGINT", nullable=False),
            "old_name": ColumnState(type="TEXT", nullable=False),
        })
        target = _state_with("t", {
            "id": ColumnState(type="BIGINT", nullable=False),
            "new_name": ColumnState(type="TEXT", nullable=False),
        })

        forward, reverse = diff_states(current, target)
        assert forward == [
            AddColumn(table="t", column="new_name", type="TEXT", nullable=False, schema="public"),
            DropColumn(table="t", column="old_name", schema="public"),
        ]
        assert reverse == [
            DropColumn(table="t", column="new_name", schema="public"),
            AddColumn(table="t", column="old_name", type="TEXT", nullable=False, schema="public"),
        ]


class TestDiffExtensions:
    def test_added_extension_yields_create_and_reverse_drop(self):
        current = SchemaState()
        target = SchemaState(extensions={"pgcrypto"})

        forward, reverse = diff_states(current, target)
        assert forward == [CreateExtension(name="pgcrypto")]
        assert reverse == [DropExtension(name="pgcrypto")]

    def test_removed_extension_yields_drop_and_reverse_create(self):
        current = SchemaState(extensions={"pgcrypto"})
        target = SchemaState()

        forward, reverse = diff_states(current, target)
        assert forward == [DropExtension(name="pgcrypto")]
        assert reverse == [CreateExtension(name="pgcrypto")]

    def test_multiple_added_extensions_are_sorted(self):
        current = SchemaState()
        target = SchemaState(extensions={"uuid-ossp", "pgcrypto"})

        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateExtension(name="pgcrypto"),
            CreateExtension(name="uuid-ossp"),
        ]
        assert reverse == [
            DropExtension(name="pgcrypto"),
            DropExtension(name="uuid-ossp"),
        ]


class TestDiffSchemas:
    def test_added_schema_yields_create_and_reverse_drop(self):
        current = SchemaState()
        target = SchemaState(schemas={"audit"})

        forward, reverse = diff_states(current, target)
        assert forward == [CreateSchema(name="audit")]
        assert reverse == [DropSchema(name="audit", cascade=False)]

    def test_removed_schema_yields_drop_and_reverse_create(self):
        current = SchemaState(schemas={"audit"})
        target = SchemaState()

        forward, reverse = diff_states(current, target)
        assert forward == [DropSchema(name="audit", cascade=False)]
        assert reverse == [CreateSchema(name="audit")]

    def test_multiple_added_schemas_are_sorted(self):
        current = SchemaState()
        target = SchemaState(schemas={"reporting", "audit"})

        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateSchema(name="audit"),
            CreateSchema(name="reporting"),
        ]
        assert reverse == [
            DropSchema(name="audit", cascade=False),
            DropSchema(name="reporting", cascade=False),
        ]


class TestDiffForwardOrdering:
    def test_extensions_before_schemas_before_tables_before_fks(self):
        current = SchemaState()
        target = SchemaState(extensions={"pgcrypto"}, schemas={"audit"})
        parent = TableState(
            columns={"id": ColumnState(type="BIGINT", nullable=False, primary_key=True)},
            schema="audit",
        )
        child = TableState(
            columns={
                "id": ColumnState(type="BIGINT", nullable=False, primary_key=True),
                "parent_id": ColumnState(type="BIGINT", nullable=False),
            },
            schema="audit",
            constraints=[
                {
                    "type": "foreign_key",
                    "name": "child_parent_id_fk",
                    "columns": ("parent_id",),
                    "references_schema": "audit",
                    "references_table": "parent",
                    "references_column": "id",
                    "on_delete": None,
                    "on_update": None,
                }
            ],
        )
        target.tables["parent"] = parent
        target.tables["child"] = child

        forward, _ = diff_states(current, target)

        assert forward == [
            CreateExtension(name="pgcrypto"),
            CreateSchema(name="audit"),
            CreateTable(
                table="child",
                columns={
                    "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                    "parent_id": ColumnDef(type="BIGINT", nullable=False),
                },
                schema="audit",
            ),
            CreateTable(
                table="parent",
                columns={
                    "id": ColumnDef(type="BIGINT", nullable=False, primary_key=True),
                },
                schema="audit",
            ),
            AddConstraint(
                table="child",
                constraint={
                    "type": "foreign_key",
                    "name": "child_parent_id_fk",
                    "columns": ("parent_id",),
                    "references_schema": "audit",
                    "references_table": "parent",
                    "references_column": "id",
                    "on_delete": None,
                    "on_update": None,
                },
                schema="audit",
            ),
        ]
