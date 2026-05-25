"""Unit tests for schema primitives: field(), TableMeta, Field types, Table/View."""

import pytest

from norm import db
from norm import TableMeta, Field, PrimaryKey, Unique, Index, Table, View, field
from .conftest import Users, UserModelExplicit


class TestField:
    def test_defaults(self):
        fd = field()
        assert fd.default is None
        assert fd.name is None

    def test_db_default(self):
        fd = field(default=db.serial())
        assert fd.default is not None

    def test_name_override(self):
        fd = field(name="user_name")
        assert fd.name == "user_name"

    def test_immutable(self):
        fd = field()
        with pytest.raises((AttributeError, TypeError)):
            fd.default = db.serial()  # type: ignore[misc]


class TestTableMeta:
    def test_stores_overrides(self):
        meta = TableMeta(table="users", schema="public")
        assert meta.table == "users"
        assert meta.schema == "public"

    def test_defaults(self):
        meta = TableMeta()
        assert meta.table is None
        assert meta.schema is not None  # sentinel: infer from module

    def test_immutable(self):
        meta = TableMeta(table="users")
        with pytest.raises((AttributeError, TypeError)):
            meta.table = "other"  # type: ignore[misc]


class TestFieldTypes:
    def test_primary_key_flag(self):
        assert isinstance(Users.id, PrimaryKey)

    def test_primary_key_db_default(self):
        assert Users.id.field_def.default is not None

    def test_index_flag(self):
        assert Users.name.field_def.index is True

    def test_unique_flag(self):
        assert Users.email.field_def.unique is True

    def test_field_no_flags(self):
        assert not isinstance(UserModelExplicit.name, PrimaryKey)
        assert UserModelExplicit.name.field_def.unique is False
        assert UserModelExplicit.name.field_def.index is False


class TestTableClass:
    def test_has_declared_columns(self):
        assert hasattr(Users, "id")
        assert hasattr(Users, "name")
        assert hasattr(Users, "email")

    def test_column_is_field(self):
        assert isinstance(Users.id, Field)
        assert isinstance(Users.name, Field)

    def test_column_is_correct_subtype(self):
        assert isinstance(Users.id, PrimaryKey)
        assert isinstance(Users.name, Index)
        assert isinstance(Users.email, Unique)

    def test_class_name_preserved(self):
        assert Users.__name__ == "Users"

    def test_direct_class_definition(self):
        class ArticleModel(Table):
            id:    PrimaryKey[int]
            title: Field[str]

        assert ArticleModel.__name__ == "ArticleModel"
        assert isinstance(ArticleModel.id, PrimaryKey)
        assert isinstance(ArticleModel.title, Field)

    def test_typo_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            _ = Users.nmae  # type: ignore[attr-defined]

    def test_view_class(self):
        class UserStats(View):
            id:    PrimaryKey[int]
            count: Field[int]

        assert UserStats.__name__ == "UserStats"
        assert isinstance(UserStats.id, PrimaryKey)
        assert isinstance(UserStats.count, Field)
