"""Unit tests for aggregation methods, group_by, and having."""

from .conftest import Users


class TestCombined:
    def test_full_aggregate_query(self):
        sql, params = (
            Users.select(
                Users.name,
                Users.id.count(distinct=True).as_("unique_users"),
                Users.age.avg().as_("avg_age"),
                Users.age.max().as_("oldest"),
                Users.age.coalesce(0).as_("age_safe"),
                Users.age.cast("float").as_("age_f"),
            )
            .group_by(Users.name)
            .having(Users.id.count() > 5)
            .build()
        )
        assert sql == (
            'SELECT "users"."name",'
            'COUNT(DISTINCT "users"."id") "unique_users",'
            'AVG("users"."age") "avg_age",'
            'MAX("users"."age") "oldest",'
            'COALESCE("users"."age",$1) "age_safe",'
            'CAST("users"."age" AS FLOAT) "age_f" '
            'FROM "public"."users" '
            'GROUP BY "users"."name" '
            'HAVING COUNT("users"."id")>$2'
        )
        assert params == (0, 5)


class TestHaving:
    def test_having_emits_having_clause(self):
        sql, params = (
            Users.select(Users.name, Users.id.count())
            .group_by(Users.name)
            .having(Users.id.count() > 5)
            .build()
        )
        assert sql == (
            'SELECT "users"."name",COUNT("users"."id") FROM "public"."users" '
            'GROUP BY "users"."name" HAVING COUNT("users"."id")>$1'
        )
        assert params == (5,)

    def test_having_returns_new_builder(self):
        base = Users.select(Users.name).group_by(Users.name)
        assert base is not base.having(Users.id.count() > 1)

    def test_having_does_not_mutate_original(self):
        base = Users.select(Users.name).group_by(Users.name)
        base.having(Users.id.count() > 1)
        sql, _ = base.build()
        assert "HAVING" not in sql


class TestGroupBy:
    def test_group_by_emits_group_by_clause(self):
        sql, params = (
            Users.select(Users.name, Users.age.count())
            .group_by(Users.name)
            .build()
        )
        assert sql == 'SELECT "users"."name",COUNT("users"."age") FROM "public"."users" GROUP BY "users"."name"'
        assert params == ()

    def test_group_by_returns_new_builder(self):
        base = Users.select(Users.name)
        assert base is not base.group_by(Users.name)

    def test_group_by_does_not_mutate_original(self):
        base = Users.select(Users.name)
        base.group_by(Users.name)
        sql, _ = base.build()
        assert "GROUP BY" not in sql


class TestAlias:
    def test_agg_field_as_renders_alias(self):
        sql, params = Users.select(Users.id.count().as_("total")).build()
        assert sql == 'SELECT COUNT("users"."id") "total" FROM "public"."users"'
        assert params == ()

    def test_coalesce_as_renders_alias(self):
        sql, params = Users.select(Users.age.coalesce(0).as_("age_safe")).build()
        assert sql == 'SELECT COALESCE("users"."age",$1) "age_safe" FROM "public"."users"'
        assert params == (0,)


class TestCast:
    def test_cast_renders_cast_expression(self):
        sql, params = Users.select(Users.age.cast("float")).build()
        assert sql == 'SELECT CAST("users"."age" AS FLOAT) FROM "public"."users"'
        assert params == ()


class TestCoalesce:
    def test_coalesce_renders_with_bound_default(self):
        sql, params = Users.select(Users.age.coalesce(0)).build()
        assert sql == 'SELECT COALESCE("users"."age",$1) FROM "public"."users"'
        assert params == (0,)


class TestAvg:
    def test_avg(self):
        sql, params = Users.select(Users.age.avg()).build()
        assert sql == 'SELECT AVG("users"."age") FROM "public"."users"'
        assert params == ()


class TestSumMinMax:
    def test_sum(self):
        sql, params = Users.select(Users.age.sum()).build()
        assert sql == 'SELECT SUM("users"."age") FROM "public"."users"'
        assert params == ()

    def test_min(self):
        sql, params = Users.select(Users.age.min()).build()
        assert sql == 'SELECT MIN("users"."age") FROM "public"."users"'
        assert params == ()

    def test_max(self):
        sql, params = Users.select(Users.age.max()).build()
        assert sql == 'SELECT MAX("users"."age") FROM "public"."users"'
        assert params == ()


class TestCount:
    def test_count_renders_in_select(self):
        sql, params = Users.select(Users.id.count()).build()
        assert sql == 'SELECT COUNT("users"."id") FROM "public"."users"'
        assert params == ()

    def test_count_distinct(self):
        sql, params = Users.select(Users.id.count(distinct=True)).build()
        assert sql == 'SELECT COUNT(DISTINCT "users"."id") FROM "public"."users"'
        assert params == ()
