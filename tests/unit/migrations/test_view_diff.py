"""Unit tests for view diff strategy (issue 145)."""

from norm.migrations.draft import diff_states
from norm.migrations.operations import CreateView, DropView
from norm.migrations.state import SchemaState, ViewState


def _state_with_view(name: str, view: ViewState) -> SchemaState:
    s = SchemaState()
    s.views[name] = view
    return s


class TestViewDiff:
    def test_view_added_emits_create_view(self):
        current = SchemaState()
        target = _state_with_view(
            "v",
            ViewState(definition="SELECT 1", columns=(("a", int),), schema="public"),
        )
        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateView(
                name="v",
                definition="SELECT 1",
                schema="public",
                columns=(("a", int),),
                replace=True,
            )
        ]
        assert reverse == [DropView(name="v", schema="public")]

    def test_view_removed_emits_drop_view(self):
        current = _state_with_view(
            "v",
            ViewState(definition="SELECT 1", columns=(("a", int),), schema="public"),
        )
        target = SchemaState()
        forward, reverse = diff_states(current, target)
        assert forward == [DropView(name="v", schema="public")]
        assert reverse == [
            CreateView(
                name="v",
                definition="SELECT 1",
                schema="public",
                columns=(("a", int),),
                replace=True,
            )
        ]

    def test_definition_changed_emits_create_or_replace(self):
        current = _state_with_view(
            "v",
            ViewState(
                definition="SELECT 1 AS a",
                columns=(("a", int),),
                schema="public",
            ),
        )
        target = _state_with_view(
            "v",
            ViewState(
                definition="SELECT 2 AS a",
                columns=(("a", int),),
                schema="public",
            ),
        )
        forward, reverse = diff_states(current, target)
        assert forward == [
            CreateView(
                name="v",
                definition="SELECT 2 AS a",
                schema="public",
                columns=(("a", int),),
                replace=True,
            )
        ]
        assert reverse == [
            CreateView(
                name="v",
                definition="SELECT 1 AS a",
                schema="public",
                columns=(("a", int),),
                replace=True,
            )
        ]

    def test_columns_changed_emits_drop_then_create(self):
        current = _state_with_view(
            "v",
            ViewState(
                definition="SELECT 1 AS a",
                columns=(("a", int),),
                schema="public",
            ),
        )
        target = _state_with_view(
            "v",
            ViewState(
                definition="SELECT 1 AS a, 2 AS b",
                columns=(("a", int), ("b", int)),
                schema="public",
            ),
        )
        forward, reverse = diff_states(current, target)
        assert forward == [
            DropView(name="v", schema="public"),
            CreateView(
                name="v",
                definition="SELECT 1 AS a, 2 AS b",
                schema="public",
                columns=(("a", int), ("b", int)),
                replace=True,
            ),
        ]
        assert reverse == [
            DropView(name="v", schema="public"),
            CreateView(
                name="v",
                definition="SELECT 1 AS a",
                schema="public",
                columns=(("a", int),),
                replace=True,
            ),
        ]

    def test_unchanged_view_emits_nothing(self):
        view = ViewState(
            definition="SELECT 1", columns=(("a", int),), schema="public",
        )
        current = _state_with_view("v", view)
        target = _state_with_view("v", view)
        forward, reverse = diff_states(current, target)
        assert forward == []
        assert reverse == []
