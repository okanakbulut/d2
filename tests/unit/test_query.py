"""Unit tests for query building: select, where, order_by, limit, offset, distinct,
column aliasing, arithmetic expressions, and insert."""

import pytest

from norm.schema import Field
from .conftest import Users, UserModelExplicit


class TestSelect:
    def test_select_returns_entity_type(self):
        result = Users.select(Users.id, Users.name, Users.email)
        assert isinstance(result, type)
        assert issubclass(result, Users)

    def test_select_all_returns_entity_type(self):
        result = Users.select_all()
        assert isinstance(result, type)
        assert issubclass(result, Users)

    def test_build_select_columns(self):
        sql, params = Users.select(Users.id, Users.name, Users.email).build()
        assert sql == 'SELECT "users"."id","users"."name","users"."email" FROM "public"."users"'
        assert params == ()

    def test_build_select_all(self):
        sql, params = Users.select_all().build()
        assert sql == 'SELECT "users"."id","users"."name","users"."email","users"."age","users"."created_at" FROM "public"."users"'
        assert params == ()

    def test_explicit_table_meta(self):
        sql, params = UserModelExplicit.select(UserModelExplicit.id).build()
        assert sql == 'SELECT "accounts_user"."id" FROM "public"."accounts_user"'
        assert params == ()


class TestWhere:
    def test_where_returns_new_entity(self):
        base = Users.select(Users.id)
        assert base is not base.where(Users.id == 1)

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

    def test_single_where(self):
        sql, params = Users.select(Users.id).where(Users.id == 42).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (42,)

    def test_multiple_where_chained_as_and(self):
        sql, params = (
            Users.select(Users.id, Users.name)
            .where(Users.id == 7)
            .where(Users.name == "alice")
            .build()
        )
        assert sql == 'SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."id"=$1 AND "users"."name"=$2'
        assert params == (7, "alice")

    def test_uses_postgres_positional_placeholders(self):
        sql, params = Users.select(Users.id).where(Users.id == 1).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (1,)


class TestOrderByLimitOffset:
    def test_order_by_asc(self):
        sql, params = Users.select(Users.id).order_by(Users.created_at).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" ORDER BY "users"."created_at" ASC'
        assert params == ()

    def test_order_by_desc(self):
        sql, params = Users.select(Users.id).order_by(Users.created_at, desc=True).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" ORDER BY "users"."created_at" DESC'
        assert params == ()

    def test_order_by_multiple_appends(self):
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

    def test_limit_immutable(self):
        base = Users.select(Users.id)
        base.limit(10)
        sql, params = base.build()
        assert sql == 'SELECT "users"."id" FROM "public"."users"'
        assert params == ()

    def test_distinct(self):
        sql, params = Users.select(Users.id).distinct().build()
        assert sql == 'SELECT DISTINCT "users"."id" FROM "public"."users"'
        assert params == ()


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


class TestArithmeticExpressions:
    def test_add_literal(self):
        sql, params = Users.select(Users.age + 100).build()
        assert sql == 'SELECT "users"."age"+$1 FROM "public"."users"'
        assert params == (100,)

    def test_sub_literal(self):
        sql, params = Users.select(Users.age - 5).build()
        assert sql == 'SELECT "users"."age"-$1 FROM "public"."users"'
        assert params == (5,)

    def test_mul_literal(self):
        sql, params = Users.select(Users.age * 2).build()
        assert sql == 'SELECT "users"."age"*$1 FROM "public"."users"'
        assert params == (2,)

    def test_div_literal(self):
        sql, params = Users.select(Users.age / 10).build()
        assert sql == 'SELECT "users"."age"/$1 FROM "public"."users"'
        assert params == (10,)

    def test_add_field_no_params(self):
        sql, params = Users.select(Users.age + Users.id).build()
        assert sql == 'SELECT "users"."age"+"users"."id" FROM "public"."users"'
        assert params == ()

    def test_arithmetic_returns_field(self):
        assert isinstance(Users.age + 1, Field)


class TestInsert:
    def test_insert_kwargs(self):
        sql, params = Users.insert(name="Alice", email="a@x.com").build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == ("Alice", "a@x.com")

    def test_insert_drops_pk_and_db_default_by_default(self):
        sql, params = Users.insert(id=99, name="Alice", email="a@x.com").build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == ("Alice", "a@x.com")

    def test_insert_exclude_defaults_false_keeps_pk(self):
        sql, params = Users.insert(id=99, name="Alice", email="a@x.com", exclude_defaults=False).build()
        assert sql == 'INSERT INTO "public"."users" ("id","name","email") VALUES ($1,$2,$3)'
        assert params == (99, "Alice", "a@x.com")

    def test_insert_bulk(self):
        sql, params = Users.insert([
            {"name": "Alice", "email": "a@x.com"},
            {"name": "Bob",   "email": "b@x.com"},
        ]).build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == [("Alice", "a@x.com"), ("Bob", "b@x.com")]

    def test_insert_bulk_empty_raises(self):
        with pytest.raises(ValueError, match="at least one row"):
            Users.insert([])

    def test_insert_bulk_inconsistent_columns_raises(self):
        with pytest.raises(ValueError, match="consistent"):
            Users.insert([
                {"name": "Alice", "email": "a@x.com"},
                {"name": "Bob"},
            ])

    def test_insert_returning(self):
        sql, params = Users.insert(name="Alice", email="a@x.com").returning(Users.id).build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) RETURNING "users"."id"'
        assert params == ("Alice", "a@x.com")

    def test_insert_returning_multiple_fields(self):
        sql, params = Users.insert(name="Alice", email="a@x.com").returning(Users.id, Users.name).build()
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) RETURNING "users"."id","users"."name"'
        assert params == ("Alice", "a@x.com")

    def test_insert_returning_is_immutable(self):
        base = Users.insert(name="Alice", email="a@x.com")
        with_returning = base.returning(Users.id)
        base_sql, _ = base.build()
        returning_sql, _ = with_returning.build()
        assert base_sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert returning_sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) RETURNING "users"."id"'
