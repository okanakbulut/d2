"""Unit tests for View(query=...) declaration + validation (issue 145)."""

import pytest

from d2.schema import Field, PrimaryKey, Table, View


class _Users(Table):
    id: PrimaryKey[int]
    email: Field[str]
    deleted_at: Field[str]


class TestViewQueryCapture:
    def test_captures_query_kwarg_on_class(self):
        query = _Users.select(_Users.id, _Users.email).where(_Users.deleted_at.isnull())

        class ActiveUsers(View, query=query):
            id: PrimaryKey[int]
            email: Field[str]

        assert ActiveUsers.__view_query__ is query


class TestViewColumnValidation:
    def test_mismatched_column_name_raises_type_error(self):
        query = _Users.select(_Users.id, _Users.email)

        with pytest.raises(TypeError) as exc:
            class Bad(View, query=query):
                id: PrimaryKey[int]
                other: Field[str]  # noqa: F841

            del Bad

        assert "other" in str(exc.value)

    def test_mismatched_column_order_raises_type_error(self):
        query = _Users.select(_Users.id, _Users.email)

        with pytest.raises(TypeError):
            class Bad(View, query=query):
                email: Field[str]
                id: PrimaryKey[int]

            del Bad

    def test_mismatched_column_type_raises_type_error(self):
        query = _Users.select(_Users.id, _Users.email)

        with pytest.raises(TypeError) as exc:
            class Bad(View, query=query):
                id: PrimaryKey[int]
                email: Field[int]  # wrong type

            del Bad

        assert "email" in str(exc.value)

    def test_matching_columns_passes(self):
        query = _Users.select(_Users.id, _Users.email)

        class Ok(View, query=query):
            id: PrimaryKey[int]
            email: Field[str]

        assert Ok.__view_query__ is query
