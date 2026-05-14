"""Unit tests for filter predicates: comparison, string, list, null, range, cross-column."""

from norm.filter import Filter
from .conftest import Users


class TestComparisonPredicates:
    def test_eq_returns_filter(self):
        assert isinstance(Users.id == 42, Filter)

    def test_eq_stores_value(self):
        assert (Users.id == 42).value == 42

    def test_eq_sql(self):
        sql, params = Users.select(Users.id).where(Users.id == 99).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (99,)

    def test_ne_returns_filter(self):
        assert isinstance(Users.id != 5, Filter)

    def test_ne_sql(self):
        sql, params = Users.select(Users.id).where(Users.id != 5).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"<>$1'
        assert params == (5,)

    def test_lt_sql(self):
        sql, params = Users.select(Users.id).where(Users.age < 30).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age"<$1'
        assert params == (30,)

    def test_lte_sql(self):
        sql, params = Users.select(Users.id).where(Users.age <= 30).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age"<=$1'
        assert params == (30,)

    def test_gt_sql(self):
        sql, params = Users.select(Users.id).where(Users.age > 18).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">$1'
        assert params == (18,)

    def test_gte_sql(self):
        sql, params = Users.select(Users.id).where(Users.age >= 18).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">=$1'
        assert params == (18,)


class TestCrossColumnComparison:
    def test_field_eq_field_no_params(self):
        sql, params = Users.select(Users.id).where(Users.id == Users.age).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id"="users"."age"'
        assert params == ()


class TestStringPredicates:
    def test_like_sql(self):
        sql, params = Users.select(Users.name).where(Users.name.like("ali%")).build()
        assert sql == 'SELECT "users"."name" FROM "public"."users" WHERE "users"."name" LIKE $1'
        assert params == ("ali%",)

    def test_ilike_sql(self):
        sql, params = Users.select(Users.name).where(Users.name.ilike("ALI%")).build()
        assert sql == 'SELECT "users"."name" FROM "public"."users" WHERE "users"."name" ILIKE $1'
        assert params == ("ALI%",)


class TestListPredicates:
    def test_isin_sql(self):
        sql, params = Users.select(Users.id).where(Users.id.isin([1, 2, 3])).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id" IN ($1,$2,$3)'
        assert params == (1, 2, 3)

    def test_notin_sql(self):
        sql, params = Users.select(Users.id).where(Users.id.notin([4, 5])).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."id" NOT IN ($1,$2)'
        assert params == (4, 5)


class TestNullPredicates:
    def test_isnull_sql(self):
        sql, params = Users.select(Users.id).where(Users.email.isnull()).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."email" IS NULL'
        assert params == ()

    def test_isnotnull_sql(self):
        sql, params = Users.select(Users.id).where(Users.email.isnotnull()).build()
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."email" IS NOT NULL'
        assert params == ()


class TestBetweenPredicate:
    def test_between_sql(self):
        sql, params = Users.select(Users.age).where(Users.age.between(18, 65)).build()
        assert sql == 'SELECT "users"."age" FROM "public"."users" WHERE "users"."age" BETWEEN $1 AND $2'
        assert params == (18, 65)
