"""Unit tests for snapshotting `View` subclasses into SchemaState (issue 145)."""

from d2.migrations.snapshot import models_to_schema_state
from d2.migrations.state import ViewState
from d2.schema import Field, PrimaryKey, Table, View


class UsersForView(Table):
    id: PrimaryKey[int]
    email: Field[str]


_users_query = UsersForView.select(UsersForView.id, UsersForView.email)


class ActiveUsersView(View, query=_users_query):
    id: PrimaryKey[int]
    email: Field[str]


class TestSnapshotView:
    def test_snapshot_includes_view_with_query_build_definition(self):
        state = models_to_schema_state([UsersForView, ActiveUsersView])
        expected_sql, _ = _users_query.build()
        assert state.views == {
            "active_users_views": ViewState(
                definition=expected_sql,
                columns=(("id", int), ("email", str)),
                schema="public",
            )
        }
