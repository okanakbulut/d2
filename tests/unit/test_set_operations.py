"""Unit tests for set operations: union, intersect, exclude."""

from typing import Any

from .conftest import Users

_ALL_COLS = '"users"."id","users"."name","users"."email","users"."age","users"."created_at"'
_FROM = 'FROM "public"."users"'


def _sel(where: str = "") -> str:
    base = f'SELECT {_ALL_COLS} {_FROM}'
    return f'({base} WHERE {where})' if where else f'({base})'


class TestUnion:
    def _both_sides(self) -> tuple[Any, Any]:
        adults = Users.select_all().where(Users.age >= 18)
        minors = Users.select_all().where(Users.age < 18)
        return adults, minors

    def test_union_produces_union_sql(self):
        adults, minors = self._both_sides()
        sql, params = adults.union(minors).build()
        assert sql == f'{_sel("\"users\".\"age\">=$1")} UNION {_sel("\"users\".\"age\"<$2")}'
        assert params == (18, 18)

    def test_union_all_uses_union_all_keyword(self):
        adults, minors = self._both_sides()
        sql, _ = adults.union(minors, all=True).build()
        assert sql == f'{_sel("\"users\".\"age\">=$1")} UNION ALL {_sel("\"users\".\"age\"<$2")}'

    def test_params_left_side_first(self):
        q1 = Users.select_all().where(Users.age >= 18)
        q2 = Users.select_all().where(Users.age < 30)
        _, params = q1.union(q2).build()
        assert params == (18, 30)

    def test_union_with_order_by_and_limit(self):
        adults, minors = self._both_sides()
        sql, params = adults.union(minors).order_by(Users.name).limit(10).build()
        expected = (
            f'{_sel("\"users\".\"age\">=$1")} UNION {_sel("\"users\".\"age\"<$2")}'
            ' ORDER BY "name" ASC LIMIT 10'
        )
        assert sql == expected
        assert params == (18, 18)

    def test_union_with_offset(self):
        adults, minors = self._both_sides()
        sql, _ = adults.union(minors).limit(5).offset(20).build()
        expected = (
            f'{_sel("\"users\".\"age\">=$1")} UNION {_sel("\"users\".\"age\"<$2")}'
            " LIMIT 5 OFFSET 20"
        )
        assert sql == expected


class TestIntersect:
    def test_intersect_produces_intersect_sql(self):
        with_email = Users.select_all().where(Users.email.isnotnull())
        adults = Users.select_all().where(Users.age >= 18)
        sql, _ = with_email.intersect(adults).build()
        assert sql == (
            f'{_sel("\"users\".\"email\" IS NOT NULL")} INTERSECT {_sel("\"users\".\"age\">=$1")}'
        )

    def test_intersect_params_left_then_right(self):
        q1 = Users.select_all().where(Users.age >= 18)
        q2 = Users.select_all().where(Users.age < 65)
        _, params = q1.intersect(q2).build()
        assert params == (18, 65)


class TestExclude:
    def test_exclude_produces_except_sql(self):
        all_users = Users.select_all()
        banned = Users.select_all().where(Users.age < 0)
        sql, _ = all_users.exclude(banned).build()
        assert sql == f'{_sel()} EXCEPT {_sel("\"users\".\"age\"<$1")}'

    def test_exclude_params_left_then_right(self):
        q1 = Users.select_all().where(Users.age >= 0)
        q2 = Users.select_all().where(Users.age < 18)
        _, params = q1.exclude(q2).build()
        assert params == (0, 18)
