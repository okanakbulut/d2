"""Reverse-completeness tests for diff_states (issue 147)."""


from d2.migrations.draft import diff_states
from d2.migrations.operations import (
    AddColumn,
    AddConstraint,
    AlterColumnType,
    CreateExtension,
    CreateIndex,
    CreateSchema,
    CreateTable,
    CreateView,
    DropColumn,
    DropColumnDefault,
    DropColumnNotNull,
    DropConstraint,
    DropExtension,
    DropIndex,
    DropSchema,
    DropTable,
    DropView,
    SetColumnDefault,
    SetColumnNotNull,
)
from d2.migrations.state import ColumnState, IndexDef, SchemaState, TableState, UniqueConstraint, ViewState


def _state(
    *,
    tables: dict[str, TableState] | None = None,
    views: dict[str, ViewState] | None = None,
    extensions: set[str] | None = None,
    schemas: set[str] | None = None,
) -> SchemaState:
    return SchemaState(
        tables=tables if tables is not None else {},
        views=views if views is not None else {},
        extensions=extensions if extensions is not None else set(),
        schemas=schemas if schemas is not None else set(),
    )


def test_drop_column_reverse_reconstructs_full_add_column_from_current_state():
    current = _state(
        tables={
            "t": TableState(
                columns={
                    "keep": ColumnState(type="BIGINT", nullable=False),
                    "victim": ColumnState(
                        type="TEXT", nullable=False, default="'x'"
                    ),
                },
                schema="public",
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"keep": ColumnState(type="BIGINT", nullable=False)},
                schema="public",
            )
        }
    )

    forward, reverse = diff_states(current, target)

    assert forward == [DropColumn(table="t", column="victim", schema="public")]
    assert reverse == [
        AddColumn(
            table="t",
            column="victim",
            type="TEXT",
            nullable=False,
            default="'x'",
            schema="public",
        )
    ]


def test_alter_column_type_reverse_uses_previous_type_from_current_state():
    current = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="INTEGER", nullable=True)},
                schema=None,
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="BIGINT", nullable=True)},
                schema=None,
            )
        }
    )

    forward, reverse = diff_states(current, target)

    assert forward == [AlterColumnType(table="t", column="x", type="BIGINT", schema=None)]
    assert reverse == [AlterColumnType(table="t", column="x", type="INTEGER", schema=None)]


def test_create_table_reverses_to_drop_table():
    current = _state()
    target = _state(
        tables={
            "t": TableState(
                columns={"id": ColumnState(type="BIGINT", nullable=False, primary_key=True)},
                schema=None,
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert reverse == [DropTable(table="t", schema=None)]
    assert isinstance(forward[0], CreateTable)


def test_add_constraint_reverses_to_drop_constraint():
    uq = UniqueConstraint(name="uq_t_id", columns=("id",))
    current = _state(
        tables={
            "t": TableState(
                columns={"id": ColumnState(type="BIGINT", nullable=False)},
                schema=None,
                constraints=[],
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"id": ColumnState(type="BIGINT", nullable=False)},
                schema=None,
                constraints=[uq],
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert forward == [
        AddConstraint(table="t", constraint=uq, schema=None)
    ]
    assert reverse == [DropConstraint(table="t", name="uq_t_id", schema=None)]


def test_create_index_reverses_to_drop_index_concurrent():
    idx = IndexDef(name="ix_t_id", columns=("id",), unique=False, method=None)
    current = _state(
        tables={
            "t": TableState(
                columns={"id": ColumnState(type="BIGINT", nullable=False)},
                schema=None,
                indexes=[],
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"id": ColumnState(type="BIGINT", nullable=False)},
                schema=None,
                indexes=[idx],
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert forward == [
        CreateIndex(
            table="t", columns=("id",), name="ix_t_id",
            method=None, unique=False, concurrent=True, schema=None,
        )
    ]
    assert reverse == [
        DropIndex(name="ix_t_id", concurrent=True, schema=None, table="t")
    ]


def test_create_extension_and_schema_reverse():
    current = _state()
    target = _state(extensions={"pgcrypto"}, schemas={"audit"})
    forward, reverse = diff_states(current, target)
    assert forward == [CreateExtension(name="pgcrypto"), CreateSchema(name="audit")]
    assert reverse == [DropExtension(name="pgcrypto"), DropSchema(name="audit", cascade=False)]


def test_create_view_reverses_to_drop_view():
    current = _state()
    target = _state(views={"v": ViewState(definition="SELECT 1", columns=(), schema=None)})
    forward, reverse = diff_states(current, target)
    assert forward == [
        CreateView(name="v", definition="SELECT 1", schema=None, columns=(), replace=True)
    ]
    assert reverse == [DropView(name="v", schema=None)]


def test_set_not_null_pair_reverses():
    current = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=True)},
                schema=None,
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=False)},
                schema=None,
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert forward == [SetColumnNotNull(table="t", column="x", schema=None)]
    assert reverse == [DropColumnNotNull(table="t", column="x", schema=None)]


def test_set_column_default_reverse_from_none_to_value():
    current = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=True, default=None)},
                schema=None,
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=True, default="'hi'")},
                schema=None,
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert forward == [SetColumnDefault(table="t", column="x", default="'hi'", schema=None)]
    assert reverse == [DropColumnDefault(table="t", column="x", schema=None)]


def test_drop_column_default_reverse_restores_previous_default():
    current = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=True, default="'old'")},
                schema=None,
            )
        }
    )
    target = _state(
        tables={
            "t": TableState(
                columns={"x": ColumnState(type="TEXT", nullable=True, default=None)},
                schema=None,
            )
        }
    )
    forward, reverse = diff_states(current, target)
    assert forward == [DropColumnDefault(table="t", column="x", schema=None)]
    assert reverse == [SetColumnDefault(table="t", column="x", default="'old'", schema=None)]
