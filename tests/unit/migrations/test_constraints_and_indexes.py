"""Unit tests for constraints + indexes (issue 143)."""

from pathlib import Path

import pytest

from norm.migrations.naming import (
    IdentifierTooLongError,
    auto_index_name,
    auto_unique_name,
)
from norm.migrations.operations import (
    AddConstraint,
    CreateIndex,
    DropConstraint,
    DropIndex,
    Operation,
)
from norm.migrations.state import (
    ColumnState,
    IndexDef,
    SchemaError,
    SchemaState,
    TableState,
    UniqueConstraint,
)


def _state_with(table: str, schema: str | None = "public") -> SchemaState:
    state = SchemaState()
    state.tables[table] = TableState(
        columns={"id": ColumnState(type="BIGINT", nullable=False)},
        schema=schema,
    )
    return state


class TestAddConstraint:
    def test_to_ddl_unique_wraps_in_do_block(self):
        op = AddConstraint(
            table="users",
            schema="public",
            constraint={
                "type": "unique",
                "name": "users_email_key",
                "columns": ("email",),
            },
        )
        expected = (
            'DO $$ BEGIN '
            'ALTER TABLE "public"."users" '
            'ADD CONSTRAINT "users_email_key" UNIQUE ("email"); '
            'EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$'
        )
        assert op.to_ddl() == expected

    def test_to_ddl_unique_multi_column(self):
        op = AddConstraint(
            table="t",
            constraint={
                "type": "unique",
                "name": "t_a_b_key",
                "columns": ("a", "b"),
            },
        )
        expected = (
            'DO $$ BEGIN '
            'ALTER TABLE "t" '
            'ADD CONSTRAINT "t_a_b_key" UNIQUE ("a", "b"); '
            'EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$'
        )
        assert op.to_ddl() == expected

    def test_apply_adds_constraint_to_state(self):
        state = _state_with("users")
        constraint = {
            "type": "unique",
            "name": "users_email_key",
            "columns": ("email",),
        }
        AddConstraint(table="users", schema="public", constraint=constraint).apply(state)
        assert state.tables["users"].constraints == [
            UniqueConstraint(name="users_email_key", columns=("email",))
        ]

    def test_apply_raises_when_table_missing(self):
        with pytest.raises(SchemaError):
            AddConstraint(
                table="missing",
                constraint={"type": "unique", "name": "x_key", "columns": ("x",)},
            ).apply(SchemaState())


class TestDropConstraint:
    def test_to_ddl_with_schema(self):
        op = DropConstraint(table="users", name="users_email_key", schema="public")
        assert (
            op.to_ddl()
            == 'ALTER TABLE "public"."users" DROP CONSTRAINT IF EXISTS "users_email_key"'
        )

    def test_to_ddl_without_schema(self):
        op = DropConstraint(table="t", name="t_x_key")
        assert op.to_ddl() == 'ALTER TABLE "t" DROP CONSTRAINT IF EXISTS "t_x_key"'

    def test_apply_removes_matching_constraint(self):
        state = _state_with("t")
        state.tables["t"].constraints = [
            UniqueConstraint(name="t_x_key", columns=("x",)),
            UniqueConstraint(name="t_y_key", columns=("y",)),
        ]
        DropConstraint(table="t", name="t_x_key").apply(state)
        assert state.tables["t"].constraints == [
            UniqueConstraint(name="t_y_key", columns=("y",)),
        ]


class TestCreateIndex:
    def test_to_ddl_defaults_concurrent_non_unique(self):
        op = CreateIndex(
            table="users",
            columns=("email",),
            name="idx_users_email",
            schema="public",
        )
        assert (
            op.to_ddl()
            == 'CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_users_email" '
            'ON "public"."users" ("email")'
        )

    def test_to_ddl_unique_no_concurrent(self):
        op = CreateIndex(
            table="t",
            columns=("a", "b"),
            name="t_a_b_key",
            unique=True,
            concurrent=False,
        )
        assert (
            op.to_ddl()
            == 'CREATE UNIQUE INDEX IF NOT EXISTS "t_a_b_key" ON "t" ("a", "b")'
        )

    def test_to_ddl_with_method(self):
        op = CreateIndex(
            table="t",
            columns=("data",),
            name="idx_t_data",
            method="gin",
            concurrent=False,
        )
        assert (
            op.to_ddl()
            == 'CREATE INDEX IF NOT EXISTS "idx_t_data" ON "t" USING gin ("data")'
        )

    def test_concurrent_defaults_to_true(self):
        op = CreateIndex(table="t", columns=("x",), name="idx_t_x")
        assert op.concurrent is True

    def test_apply_adds_index_to_state(self):
        state = _state_with("t")
        CreateIndex(
            table="t",
            columns=("x",),
            name="idx_t_x",
            unique=False,
        ).apply(state)
        assert state.tables["t"].indexes == [
            IndexDef(name="idx_t_x", columns=("x",), unique=False, method=None),
        ]


class TestDropIndex:
    def test_to_ddl_defaults_concurrent(self):
        op = DropIndex(name="idx_users_email", schema="public")
        assert op.to_ddl() == 'DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_users_email"'

    def test_to_ddl_non_concurrent_no_schema(self):
        op = DropIndex(name="idx_t_x", concurrent=False)
        assert op.to_ddl() == 'DROP INDEX IF EXISTS "idx_t_x"'

    def test_concurrent_defaults_to_true(self):
        op = DropIndex(name="idx_t_x")
        assert op.concurrent is True

    def test_apply_removes_matching_index(self):
        state = _state_with("t")
        state.tables["t"].indexes = [
            IndexDef(name="idx_t_x", columns=("x",), unique=False, method=None),
            IndexDef(name="idx_t_y", columns=("y",), unique=False, method=None),
        ]
        DropIndex(name="idx_t_x").apply(state)
        assert state.tables["t"].indexes == [
            IndexDef(name="idx_t_y", columns=("y",), unique=False, method=None),
        ]


class TestCheckWarnsOnAtomicMismatch:
    def test_check_warns_and_exits_non_zero_when_atomic_true_with_concurrent_op(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import sys

        from norm.migrations.__main__ import cmd_check

        (tmp_path / "pyproject.toml").write_text("[tool.norm]\n")
        (tmp_path / "models.py").write_text("")
        migs = tmp_path / "migrations"
        migs.mkdir()
        (migs / "0001_bad.py").write_text(
            "from norm.migrations import Migration\n"
            "from norm.migrations.operations import ColumnDef, CreateIndex, CreateTable\n"
            "\n"
            "class Migration(Migration):\n"
            "    name = '0001_bad'\n"
            "    dependencies = []\n"
            "    atomic = True\n"
            "    operations = [\n"
            "        CreateTable(table='t', columns={'x': ColumnDef(type='TEXT', nullable=False)}),\n"
            "        CreateIndex(table='t', columns=('x',), name='idx_t_x', concurrent=True),\n"
            "    ]\n"
            "    reverse_operations = []\n"
        )

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_check(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc != 0
        out = capsys.readouterr().out
        assert "0001_bad" in out
        assert "atomic = True" in out
        assert "CONCURRENTLY" in out


class TestSnapshotConstraintsAndIndexes:
    def test_field_unique_produces_constraint_in_snapshot(self):
        from norm.migrations.snapshot import models_to_schema_state
        from norm.model import field
        from norm.schema import Field, Table

        class SnapUniqueUser(Table):
            email: Field[str] = field(unique=True)

        state = models_to_schema_state([SnapUniqueUser])
        t = state.tables["snap_unique_users"]
        assert t.constraints == [
            UniqueConstraint(name="snap_unique_users_email_key", columns=("email",))
        ]
        assert t.indexes == []

    def test_field_index_produces_index_in_snapshot(self):
        from norm.migrations.snapshot import models_to_schema_state
        from norm.model import field
        from norm.schema import Field, Table

        class SnapIndexedUser(Table):
            email: Field[str] = field(index=True)

        state = models_to_schema_state([SnapIndexedUser])
        t = state.tables["snap_indexed_users"]
        assert t.constraints == []
        assert t.indexes == [
            IndexDef(name="idx_snap_indexed_users_email", columns=("email",), unique=False, method=None)
        ]

    def test_table_meta_indexes_added_to_snapshot(self):
        import norm.model as _model
        from norm.migrations.snapshot import models_to_schema_state
        from norm.schema import Field, Table

        class SnapEvent(Table):
            __meta__ = _model.TableMeta(
                indexes=(
                    _model.IndexDef(columns=("a", "b"), name="idx_snap_event_a_b"),
                ),
            )
            a: Field[str]
            b: Field[str]

        state = models_to_schema_state([SnapEvent])
        t = state.tables["snap_events"]
        assert t.indexes == [
            IndexDef(name="idx_snap_event_a_b", columns=("a", "b"), unique=False, method=None)
        ]


class TestDiffConstraintsAndIndexes:
    def test_new_unique_constraint_yields_add_and_reverse_drop(self):
        from norm.migrations.draft import diff_states

        current = SchemaState()
        current.tables["t"] = TableState(
            columns={"email": ColumnState(type="TEXT", nullable=False)},
            schema="public",
        )
        target = SchemaState()
        target.tables["t"] = TableState(
            columns={"email": ColumnState(type="TEXT", nullable=False)},
            schema="public",
            constraints=[UniqueConstraint(name="t_email_key", columns=("email",))],
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            AddConstraint(
                table="t",
                constraint=UniqueConstraint(name="t_email_key", columns=("email",)),
                schema="public",
            )
        ]
        assert reverse == [
            DropConstraint(table="t", name="t_email_key", schema="public"),
        ]

    def test_dropped_unique_constraint_yields_drop_and_reverse_add(self):
        from norm.migrations.draft import diff_states

        constraint = UniqueConstraint(name="t_email_key", columns=("email",))
        current = SchemaState()
        current.tables["t"] = TableState(
            columns={"email": ColumnState(type="TEXT", nullable=False)},
            schema="public",
            constraints=[constraint],
        )
        target = SchemaState()
        target.tables["t"] = TableState(
            columns={"email": ColumnState(type="TEXT", nullable=False)},
            schema="public",
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            DropConstraint(table="t", name="t_email_key", schema="public"),
        ]
        assert reverse == [
            AddConstraint(table="t", constraint=constraint, schema="public"),
        ]

    def test_new_index_yields_create_and_reverse_drop(self):
        from norm.migrations.draft import diff_states

        current = SchemaState()
        current.tables["t"] = TableState(
            columns={"x": ColumnState(type="TEXT", nullable=False)},
            schema="public",
        )
        target = SchemaState()
        target.tables["t"] = TableState(
            columns={"x": ColumnState(type="TEXT", nullable=False)},
            schema="public",
            indexes=[IndexDef(name="idx_t_x", columns=("x",), unique=False, method=None)],
        )

        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateIndex(
                table="t",
                columns=("x",),
                name="idx_t_x",
                method=None,
                unique=False,
                concurrent=True,
                schema="public",
            )
        ]
        assert reverse == [DropIndex(name="idx_t_x", concurrent=True, schema="public", table="t")]

    def test_dropped_index_yields_drop_and_reverse_create(self):
        from norm.migrations.draft import diff_states

        idx = IndexDef(name="idx_t_x", columns=("x",), unique=False, method=None)
        current = SchemaState()
        current.tables["t"] = TableState(
            columns={"x": ColumnState(type="TEXT", nullable=False)},
            schema="public",
            indexes=[idx],
        )
        target = SchemaState()
        target.tables["t"] = TableState(
            columns={"x": ColumnState(type="TEXT", nullable=False)},
            schema="public",
        )

        forward, reverse = diff_states(current, target)
        assert forward == [DropIndex(name="idx_t_x", concurrent=True, schema="public", table="t")]
        assert reverse == [
            CreateIndex(
                table="t",
                columns=("x",),
                name="idx_t_x",
                method=None,
                unique=False,
                concurrent=True,
                schema="public",
            )
        ]


EXPECTED_CODEGEN_ATOMIC_FALSE = '''from norm.migrations import Migration
from norm.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateExtension, CreateIndex, CreateSchema, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropExtension, DropIndex, DropSchema, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull

# atomic = False because this migration contains non-transactional operations (CONCURRENTLY).

class Migration(Migration):
    name = "0002_auto"
    dependencies = ["0001_init"]
    atomic = False
    operations = [
        AddConstraint(table="users", constraint={"type": "unique", "name": "users_email_key", "columns": ("email",)}, schema="public"),
        CreateIndex(table="users", columns=("name",), name="idx_users_name", method=None, unique=False, concurrent=True, schema="public"),
        DropConstraint(table="users", name="old_key", schema="public"),
        DropIndex(name="old_idx", concurrent=True, schema="public", table="users"),
    ]
    reverse_operations = [
        DropConstraint(table="users", name="users_email_key", schema="public"),
        DropIndex(name="idx_users_name", concurrent=True, schema="public", table="users"),
        AddConstraint(table="users", constraint={"type": "unique", "name": "old_key", "columns": ("legacy",)}, schema="public"),
        CreateIndex(table="users", columns=("legacy",), name="old_idx", method=None, unique=False, concurrent=True, schema="public"),
    ]
'''


EXPECTED_CODEGEN_ATOMIC_TRUE = '''from norm.migrations import Migration
from norm.migrations.operations import AddColumn, AddConstraint, AlterColumnType, ColumnDef, CreateExtension, CreateIndex, CreateSchema, CreateTable, CreateView, DropColumn, DropColumnDefault, DropColumnNotNull, DropConstraint, DropExtension, DropIndex, DropSchema, DropTable, DropView, RenameColumn, SetColumnDefault, SetColumnNotNull


class Migration(Migration):
    name = "0002_auto"
    dependencies = ["0001_init"]
    operations = [
        AddConstraint(table="t", constraint={"type": "unique", "name": "t_x_key", "columns": ("x",)}, schema=None),
    ]
    reverse_operations = [
        DropConstraint(table="t", name="t_x_key", schema=None),
    ]
'''


class TestCodegenConstraintsAndIndexes:
    def test_renders_non_atomic_with_comment_when_concurrent_ops_present(
        self, tmp_path: Path
    ) -> None:
        from norm.migrations.codegen import make_migration

        forward: list[Operation] = [
            AddConstraint(
                table="users",
                constraint={"type": "unique", "name": "users_email_key", "columns": ("email",)},
                schema="public",
            ),
            CreateIndex(
                table="users",
                columns=("name",),
                name="idx_users_name",
                method=None,
                unique=False,
                concurrent=True,
                schema="public",
            ),
            DropConstraint(table="users", name="old_key", schema="public"),
            DropIndex(name="old_idx", concurrent=True, schema="public", table="users"),
        ]
        reverse: list[Operation] = [
            DropConstraint(table="users", name="users_email_key", schema="public"),
            DropIndex(name="idx_users_name", concurrent=True, schema="public", table="users"),
            AddConstraint(
                table="users",
                constraint={"type": "unique", "name": "old_key", "columns": ("legacy",)},
                schema="public",
            ),
            CreateIndex(
                table="users",
                columns=("legacy",),
                name="old_idx",
                method=None,
                unique=False,
                concurrent=True,
                schema="public",
            ),
        ]
        path = make_migration(
            migrations_dir=tmp_path,
            number=2,
            forward=forward,
            reverse=reverse,
            dependencies=["0001_init"],
            label=None,
        )
        assert path.read_text() == EXPECTED_CODEGEN_ATOMIC_FALSE

    def test_renders_atomic_true_when_only_constraint_ops(self, tmp_path: Path) -> None:
        from norm.migrations.codegen import make_migration

        forward: list[Operation] = [
            AddConstraint(
                table="t",
                constraint={"type": "unique", "name": "t_x_key", "columns": ("x",)},
                schema=None,
            ),
        ]
        reverse: list[Operation] = [DropConstraint(table="t", name="t_x_key", schema=None)]
        path = make_migration(
            migrations_dir=tmp_path,
            number=2,
            forward=forward,
            reverse=reverse,
            dependencies=["0001_init"],
            label=None,
        )
        assert path.read_text() == EXPECTED_CODEGEN_ATOMIC_TRUE


class TestAutoNaming:
    def test_index_name_single_column(self):
        assert auto_index_name("users", ("email",)) == "idx_users_email"

    def test_index_name_multi_column(self):
        assert auto_index_name("orders", ("a", "b")) == "idx_orders_a_b"

    def test_unique_name_single_column(self):
        assert auto_unique_name("users", ("email",)) == "users_email_key"

    def test_unique_name_multi_column(self):
        assert auto_unique_name("t", ("a", "b")) == "t_a_b_key"

    def test_index_name_too_long_raises_pointing_at_name_kwarg(self):
        long_table = "t" * 55
        with pytest.raises(IdentifierTooLongError) as exc:
            auto_index_name(long_table, ("col_one", "col_two"))
        assert "name=" in str(exc.value)

    def test_unique_name_too_long_raises_pointing_at_name_kwarg(self):
        long_table = "t" * 55
        with pytest.raises(IdentifierTooLongError) as exc:
            auto_unique_name(long_table, ("col_one", "col_two"))
        assert "name=" in str(exc.value)
