"""Unit tests — no database connection required."""

import pytest

from norm import TableMeta, Field, PrimaryKey, Unique, Index, Table, View, field


# ---------------------------------------------------------------------------
# Shared test models
# ---------------------------------------------------------------------------

class UserModel(Table):
    id:    PrimaryKey[int] = field(db_default=True)
    name:  Index[str]
    email: Unique[str]


class UserModelExplicit(Table):
    __meta__ = TableMeta(table="accounts_user", schema="public")
    id:    PrimaryKey[int]
    name:  Field[str]


# ---------------------------------------------------------------------------
# Cycle 1 — field() / FieldDef
# ---------------------------------------------------------------------------

class TestField:
    def test_defaults(self):
        fd = field()
        assert fd.db_default is False
        assert fd.name is None

    def test_db_default(self):
        fd = field(db_default=True)
        assert fd.db_default is True

    def test_name_override(self):
        fd = field(name="user_name")
        assert fd.name == "user_name"

    def test_immutable(self):
        fd = field()
        with pytest.raises((AttributeError, TypeError)):
            fd.db_default = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cycle 2 — TableMeta
# ---------------------------------------------------------------------------

class TestTableMeta:
    def test_stores_overrides(self):
        meta = TableMeta(table="users", schema="public")
        assert meta.table == "users"
        assert meta.schema == "public"

    def test_defaults_none(self):
        meta = TableMeta()
        assert meta.table is None
        assert meta.schema is None

    def test_immutable(self):
        meta = TableMeta(table="users")
        with pytest.raises((AttributeError, TypeError)):
            meta.table = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cycle 3 — Field types map to correct FieldDef flags
# ---------------------------------------------------------------------------

class TestFieldTypes:
    def test_primary_key_flag(self):
        assert UserModel.id.field_def.primary_key is True

    def test_primary_key_db_default(self):
        assert UserModel.id.field_def.db_default is True

    def test_index_flag(self):
        assert UserModel.name.field_def.index is True

    def test_unique_flag(self):
        assert UserModel.email.field_def.unique is True

    def test_field_no_flags(self):
        assert UserModelExplicit.name.field_def.primary_key is False
        assert UserModelExplicit.name.field_def.unique is False
        assert UserModelExplicit.name.field_def.index is False


# ---------------------------------------------------------------------------
# Cycle 4 — Table class with typed column attributes
# ---------------------------------------------------------------------------

class TestTableClass:
    def test_has_declared_columns(self):
        assert hasattr(UserModel, "id")
        assert hasattr(UserModel, "name")
        assert hasattr(UserModel, "email")

    def test_column_is_field(self):
        assert isinstance(UserModel.id, Field)
        assert isinstance(UserModel.name, Field)

    def test_column_is_correct_subtype(self):
        assert isinstance(UserModel.id, PrimaryKey)
        assert isinstance(UserModel.name, Index)
        assert isinstance(UserModel.email, Unique)

    def test_class_name_preserved(self):
        assert UserModel.__name__ == "UserModel"

    def test_direct_class_definition(self):
        class ArticleModel(Table):
            id:    PrimaryKey[int]
            title: Field[str]

        assert ArticleModel.__name__ == "ArticleModel"
        assert isinstance(ArticleModel.id, PrimaryKey)
        assert isinstance(ArticleModel.title, Field)

    def test_typo_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            _ = UserModel.nmae  # type: ignore[attr-defined]

    def test_view_class(self):
        class UserStats(View):
            id:    PrimaryKey[int]
            count: Field[int]

        assert UserStats.__name__ == "UserStats"
        assert isinstance(UserStats.id, PrimaryKey)
        assert isinstance(UserStats.count, Field)


# ---------------------------------------------------------------------------
# Cycle 5 — Field predicates
# ---------------------------------------------------------------------------

class TestFieldPredicates:
    def test_eq_returns_criterion_not_bool(self):
        from norm.filter import Filter
        criterion = UserModel.id == 42
        assert isinstance(criterion, Filter)

    def test_eq_stores_value(self):
        criterion = UserModel.id == 42
        assert criterion.value == 42

    def test_eq_value_is_never_in_sql(self):
        """Literal values must never appear in the SQL string."""
        q = UserModel.select(UserModel.id).where(UserModel.id == 99)
        sql, params = q.build()
        assert "99" not in sql
        assert 99 in params


# ---------------------------------------------------------------------------
# Cycles 6–9 — QueryBuilder
# ---------------------------------------------------------------------------

class TestQueryBuilder:
    def test_select_returns_query_builder(self):
        from norm.query import QueryBuilder
        q = UserModel.select(UserModel.id, UserModel.name, UserModel.email)
        assert isinstance(q, QueryBuilder)

    def test_select_all_returns_query_builder(self):
        from norm.query import QueryBuilder
        q = UserModel.select_all()
        assert isinstance(q, QueryBuilder)

    def test_where_returns_new_query_builder(self):
        base = UserModel.select(UserModel.id)
        refined = base.where(UserModel.id == 1)
        assert base is not refined

    def test_where_does_not_mutate_original(self):
        base = UserModel.select(UserModel.id)
        base.where(UserModel.id == 1)
        sql, params = base.build()
        assert "WHERE" not in sql
        assert params == ()

    def test_query_builder_is_immutable(self):
        q = UserModel.select(UserModel.id)
        with pytest.raises(AttributeError):
            q.filters = ()  # type: ignore[misc]

    def test_build_select_columns(self):
        sql, params = UserModel.select(UserModel.id, UserModel.name, UserModel.email).build()
        assert '"id"' in sql
        assert '"name"' in sql
        assert '"email"' in sql
        assert params == ()

    def test_build_select_all(self):
        sql, _ = UserModel.select_all().build()
        assert '"id"' in sql
        assert '"name"' in sql
        assert '"email"' in sql

    def test_build_where_positional_placeholder(self):
        sql, params = UserModel.select(UserModel.id).where(UserModel.id == 42).build()
        assert "$1" in sql
        assert params == (42,)

    def test_build_where_multiple_params(self):
        q = UserModel.select(UserModel.id, UserModel.name).where(UserModel.id == 7).where(UserModel.name == "alice")
        sql, params = q.build()
        assert "$1" in sql
        assert "$2" in sql
        assert params == (7, "alice")

    def test_build_no_literal_values_in_sql(self):
        sql, _ = UserModel.select(UserModel.id).where(UserModel.id == 42).build()
        assert "42" not in sql

    def test_build_full_example(self):
        q = UserModel.select(UserModel.id, UserModel.name, UserModel.email).where(UserModel.id == 42)
        sql, params = q.build()
        assert '"id"' in sql and '"name"' in sql and '"email"' in sql
        assert "WHERE" in sql
        assert "$1" in sql
        assert params == (42,)

    def test_build_with_explicit_table_meta(self):
        sql, _ = UserModelExplicit.select(UserModelExplicit.id).build()
        assert '"accounts_user"' in sql
        assert '"public"' in sql

    def test_default_build_uses_postgres_placeholders(self):
        sql, params = UserModel.select(UserModel.id).where(UserModel.id == 1).build()
        assert "$1" in sql
        assert params == (1,)
