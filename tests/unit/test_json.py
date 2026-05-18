"""Tests for .json() query modifier."""

from tests.unit.conftest import Users, Posts


def test_json_single_row():
    sql, params = Users.select(Users.id, Users.name).json().build()
    assert sql == (
        'SELECT row_to_json(t) FROM (SELECT "users"."id","users"."name" FROM "public"."users") t'
    )
    assert params == ()


def test_json_with_where():
    sql, params = (
        Users.select(Users.id, Users.name)
        .where(Users.id == 1)
        .json()
        .build()
    )
    assert sql == (
        'SELECT row_to_json(t) FROM '
        '(SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."id"=$1) t'
    )
    assert params == (1,)


def test_json_with_limit():
    sql, params = Users.select_all().limit(1).json().build()
    assert sql == (
        'SELECT row_to_json(t) FROM '
        '(SELECT "users"."id","users"."name","users"."email","users"."age","users"."created_at"'
        ' FROM "public"."users" LIMIT 1) t'
    )
    assert params == ()


def test_json_aliased_returns_object_with_array():
    sql, params = Users.select(Users.id, Users.name).aliased("users").json().build()
    assert sql == (
        "SELECT json_build_object('users',COALESCE(json_agg(t),'[]'::json)) "
        'FROM (SELECT "users"."id","users"."name" FROM "public"."users") t'
    )
    assert params == ()


def test_json_aliased_with_where():
    sql, params = (
        Users.select(Users.id, Users.name)
        .where(Users.age > 18)
        .aliased("adults")
        .json()
        .build()
    )
    assert sql == (
        "SELECT json_build_object('adults',COALESCE(json_agg(t),'[]'::json)) "
        'FROM (SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."age">$1) t'
    )
    assert params == (18,)


def test_json_select_all():
    sql, params = Users.select_all().json().build()
    assert sql == (
        'SELECT row_to_json(t) FROM '
        '(SELECT "users"."id","users"."name","users"."email","users"."age","users"."created_at"'
        ' FROM "public"."users") t'
    )
    assert params == ()


