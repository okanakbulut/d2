"""Unit tests — no database connection required."""

import pytest

from norm import TableMeta, Field, PrimaryKey, Unique, Index, Table, View, field


# ---------------------------------------------------------------------------
# Shared test models
# ---------------------------------------------------------------------------

class Users(Table):
    __meta__ = TableMeta(schema="public")
    id:         PrimaryKey[int] = field(db_default=True)
    name:       Index[str]
    email:      Unique[str]
    age:        Field[int]
    created_at: Field[str]


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
        assert Users.id.field_def.primary_key is True

    def test_primary_key_db_default(self):
        assert Users.id.field_def.db_default is True

    def test_index_flag(self):
        assert Users.name.field_def.index is True

    def test_unique_flag(self):
        assert Users.email.field_def.unique is True

    def test_field_no_flags(self):
        assert UserModelExplicit.name.field_def.primary_key is False
        assert UserModelExplicit.name.field_def.unique is False
        assert UserModelExplicit.name.field_def.index is False


# ---------------------------------------------------------------------------
# Cycle 4 — Table class with typed column attributes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Cycle 5 — Field predicates
# ---------------------------------------------------------------------------

class TestFieldPredicates:
    def test_eq_returns_criterion_not_bool(self):
        from norm.filter import Filter
        criterion = Users.id == 42
        assert isinstance(criterion, Filter)

    def test_eq_stores_value(self):
        criterion = Users.id == 42
        assert criterion.value == 42

    def test_eq_value_bound_as_param(self):
        sql, params = Users.select(Users.id).where(Users.id == 99).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (99,)


# ---------------------------------------------------------------------------
# Cycles 6–9 — QueryBuilder
# ---------------------------------------------------------------------------

class TestQueryBuilder:
    def test_select_returns_entity_type(self):
        q = Users.select(Users.id, Users.name, Users.email)
        assert isinstance(q, type)
        assert issubclass(q, Users)

    def test_select_all_returns_entity_type(self):
        q = Users.select_all()
        assert isinstance(q, type)
        assert issubclass(q, Users)

    def test_where_returns_new_query_builder(self):
        base = Users.select(Users.id)
        refined = base.where(Users.id == 1)
        assert base is not refined

    def test_where_does_not_mutate_original(self):
        base = Users.select(Users.id)
        base.where(Users.id == 1)
        sql, params = base.build()
        assert sql == 'SELECT "users"."id" FROM "public"."users"'
        assert params == ()

    def test_original_filters_unchanged_after_where(self):
        q = Users.select(Users.id)
        q.where(Users.id == 1)
        assert q.__filters__ == ()

    def test_build_select_columns(self):
        sql, params = Users.select(Users.id, Users.name, Users.email).build()
        assert sql == 'SELECT "users"."id","users"."name","users"."email" FROM "public"."users"'
        assert params == ()

    def test_build_select_all(self):
        sql, params = Users.select_all().build()
        assert sql == 'SELECT "users"."id","users"."name","users"."email","users"."age","users"."created_at" FROM "public"."users"'
        assert params == ()

    def test_build_where_positional_placeholder(self):
        sql, params = Users.select(Users.id).where(Users.id == 42).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (42,)

    def test_build_where_multiple_params(self):
        sql, params = (
            Users.select(Users.id, Users.name)
            .where(Users.id == 7)
            .where(Users.name == "alice")
            .build()
        )
        assert sql == 'SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."id"=$1 AND "users"."name"=$2'
        assert params == (7, "alice")

    def test_build_full_example(self):
        sql, params = (
            Users.select(Users.id, Users.name, Users.email)
            .where(Users.id == 42)
            .build()
        )
        assert sql == 'SELECT "users"."id","users"."name","users"."email" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (42,)

    def test_build_with_explicit_table_meta(self):
        sql, params = UserModelExplicit.select(UserModelExplicit.id).build()
        assert sql == 'SELECT "accounts_user"."id" FROM "public"."accounts_user"'
        assert params == ()

    def test_default_build_uses_postgres_placeholders(self):
        sql, params = Users.select(Users.id).where(Users.id == 1).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (1,)


# ---------------------------------------------------------------------------
# Cycle 10 — Comparison predicates: !=, <, <=, >, >=
# ---------------------------------------------------------------------------

class TestComparisonPredicates:
    def test_ne_produces_filter(self):
        from norm.filter import Filter
        criterion = Users.id != 5
        assert isinstance(criterion, Filter)

    def test_ne_renders_not_equal(self):
        sql, params = Users.select(Users.id).where(Users.id != 5).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"<>$1'
        assert params == (5,)

    def test_lt_renders_less_than(self):
        sql, params = Users.select(Users.id).where(Users.age < 30).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age"<$1'
        assert params == (30,)

    def test_lte_renders_less_than_or_equal(self):
        sql, params = Users.select(Users.id).where(Users.age <= 30).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age"<=$1'
        assert params == (30,)

    def test_gt_renders_greater_than(self):
        sql, params = Users.select(Users.id).where(Users.age > 18).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">$1'
        assert params == (18,)

    def test_gte_renders_greater_than_or_equal(self):
        sql, params = Users.select(Users.id).where(Users.age >= 18).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">=$1'
        assert params == (18,)


# ---------------------------------------------------------------------------
# Cycle 11 — Field == Field cross-column comparison
# ---------------------------------------------------------------------------

class TestCrossColumnComparison:
    def test_field_eq_field_renders_column_comparison(self):
        sql, params = (
            Users.select(Users.id)
            .where(Users.id == Users.age)
            .build()
        )
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"="users"."age"'
        assert params == ()


# ---------------------------------------------------------------------------
# Cycle 12 — String predicates: like / ilike
# ---------------------------------------------------------------------------

class TestStringPredicates:
    def test_like_renders_like(self):
        sql, params = Users.select(Users.name).where(Users.name.like("ali%")).build()
        assert sql == 'SELECT "users"."name" FROM "public"."users" WHERE "users"."name" LIKE $1'
        assert params == ("ali%",)

    def test_ilike_renders_ilike(self):
        sql, params = Users.select(Users.name).where(Users.name.ilike("ALI%")).build()
        assert sql == 'SELECT "users"."name" FROM "public"."users" WHERE "users"."name" ILIKE $1'
        assert params == ("ALI%",)


# ---------------------------------------------------------------------------
# Cycle 13 — List predicates: isin / notin
# ---------------------------------------------------------------------------

class TestListPredicates:
    def test_isin_renders_in(self):
        sql, params = Users.select(Users.id).where(Users.id.isin([1, 2, 3])).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id" IN ($1,$2,$3)'
        assert params == (1, 2, 3)

    def test_notin_renders_not_in(self):
        sql, params = Users.select(Users.id).where(Users.id.notin([4, 5])).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id" NOT IN ($1,$2)'
        assert params == (4, 5)


# ---------------------------------------------------------------------------
# Cycle 14 — Null predicates: isnull / isnotnull
# ---------------------------------------------------------------------------

class TestNullPredicates:
    def test_isnull_renders_is_null(self):
        sql, params = Users.select(Users.id).where(Users.email.isnull()).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."email" IS NULL'
        assert params == ()

    def test_isnotnull_renders_is_not_null(self):
        sql, params = Users.select(Users.id).where(Users.email.isnotnull()).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."email" IS NOT NULL'
        assert params == ()


# ---------------------------------------------------------------------------
# Cycle 15 — Range predicate: between
# ---------------------------------------------------------------------------

class TestBetweenPredicate:
    def test_between_renders_between(self):
        sql, params = Users.select(Users.age).where(Users.age.between(18, 65)).build()
        assert sql == 'SELECT "users"."age" FROM "public"."users" WHERE "users"."age" BETWEEN $1 AND $2'
        assert params == (18, 65)


# ---------------------------------------------------------------------------
# Cycle 16 — Column aliasing: as_
# ---------------------------------------------------------------------------

class TestColumnAliasing:
    def test_as_renders_alias_in_select(self):
        sql, params = Users.select(Users.name.aliased("display_name")).build()
        assert sql == 'SELECT "users"."name" "display_name" FROM "public"."users"'
        assert params == ()

    def test_as_does_not_mutate_original(self):
        aliased = Users.name.aliased("display_name")
        sql, params = Users.select(Users.name).build()
        assert sql == 'SELECT "users"."name" FROM "public"."users"'
        assert params == ()
        assert aliased is not Users.name


# ---------------------------------------------------------------------------
# Cycle 17 — Arithmetic operators
# ---------------------------------------------------------------------------

class TestArithmeticOperators:
    def test_add_literal_binds_as_param(self):
        sql, params = Users.select(Users.age + 100).build()
        assert sql == 'SELECT "users"."age"+$1 FROM "public"."users"'
        assert params == (100,)

    def test_sub_literal_binds_as_param(self):
        sql, params = Users.select(Users.age - 5).build()
        assert sql == 'SELECT "users"."age"-$1 FROM "public"."users"'
        assert params == (5,)

    def test_mul_literal_binds_as_param(self):
        sql, params = Users.select(Users.age * 2).build()
        assert sql == 'SELECT "users"."age"*$1 FROM "public"."users"'
        assert params == (2,)

    def test_div_literal_binds_as_param(self):
        sql, params = Users.select(Users.age / 10).build()
        assert sql == 'SELECT "users"."age"/$1 FROM "public"."users"'
        assert params == (10,)

    def test_add_field_no_params(self):
        sql, params = Users.select(Users.age + Users.id).build()
        assert sql == 'SELECT "users"."age"+"users"."id" FROM "public"."users"'
        assert params == ()

    def test_arithmetic_returns_field(self):
        from norm.schema import Field
        expr = Users.age + 1
        assert isinstance(expr, Field)


# ---------------------------------------------------------------------------
# Cycle 18 — QueryBuilder: order_by, limit, offset, distinct
# ---------------------------------------------------------------------------

class TestQueryBuilderOrdering:
    def test_order_by_asc(self):
        sql, params = Users.select(Users.id).order_by(Users.created_at).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" ORDER BY "users"."created_at" ASC'
        assert params == ()

    def test_order_by_desc(self):
        sql, params = Users.select(Users.id).order_by(Users.created_at, desc=True).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" ORDER BY "users"."created_at" DESC'
        assert params == ()

    def test_order_by_multiple_calls_append(self):
        sql, params = (
            Users.select(Users.id)
            .order_by(Users.name)
            .order_by(Users.age, desc=True)
            .build()
        )
        assert sql == 'SELECT "users"."id" FROM "public"."users" ORDER BY "users"."name" ASC,"users"."age" DESC'
        assert params == ()

    def test_order_by_immutable(self):
        base = Users.select(Users.id)
        refined = base.order_by(Users.name)
        assert base is not refined
        sql, params = base.build()
        assert sql == 'SELECT "users"."id" FROM "public"."users"'
        assert params == ()

    def test_limit(self):
        sql, params = Users.select(Users.id).limit(50).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" LIMIT 50'
        assert params == ()

    def test_offset(self):
        sql, params = Users.select(Users.id).offset(100).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" OFFSET 100'
        assert params == ()

    def test_distinct(self):
        sql, params = Users.select(Users.id).distinct().build()
        assert sql == 'SELECT DISTINCT "users"."id" FROM "public"."users"'
        assert params == ()

    def test_limit_immutable(self):
        base = Users.select(Users.id)
        base.limit(10)
        sql, params = base.build()
        assert sql == 'SELECT "users"."id" FROM "public"."users"'
        assert params == ()


# ---------------------------------------------------------------------------
# Cycle 19 — Table.insert single-row builds INSERT SQL
# ---------------------------------------------------------------------------

class TestInsertSingleRow:
    def test_insert_builds_sql(self):
        q = Users.insert(name="Alice", email="a@x.com")
        sql, params = q.build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == ("Alice", "a@x.com")


# ---------------------------------------------------------------------------
# Cycle 20 — Table.insert list-of-dicts builds same SQL, nested params
# ---------------------------------------------------------------------------

class TestInsertMultiRow:
    def test_insert_many_builds_sql_and_param_list(self):
        q = Users.insert([
            {"name": "Alice", "email": "a@x.com"},
            {"name": "Bob",   "email": "b@x.com"},
        ])
        sql, params = q.build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == [("Alice", "a@x.com"), ("Bob", "b@x.com")]



