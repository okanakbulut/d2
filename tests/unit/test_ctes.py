"""Unit tests for With — named and recursive CTEs."""

from norm import With
from .conftest import Users, Posts, Orders, Employees


class TestNamedCTE:
    def test_single_named_cte_sql(self):
        recent_posts = Posts.select(Posts.user_id, Posts.title).aliased("recent_posts")
        q = With(
            recent_posts,
            query=(
                Users.select(Users.name, recent_posts.user_id)
                .join(recent_posts, on=Users.id == recent_posts.user_id)
            ),
        )
        sql, params = q.build()
        assert sql == (
            'WITH "recent_posts" AS ('
            'SELECT "posts"."user_id","posts"."title" FROM "public"."posts"'
            ') SELECT "users"."name","recent_posts"."user_id" FROM "public"."users"'
            ' JOIN "recent_posts" ON "users"."id"="recent_posts"."user_id"'
        )
        assert params == ()

    def test_cte_with_title_column(self):
        recent_posts = Posts.select(Posts.user_id, Posts.title).aliased("recent_posts")
        q = With(
            recent_posts,
            query=(
                Users.select(Users.name, recent_posts.title)
                .join(recent_posts, on=Users.id == recent_posts.user_id)
            ),
        )
        sql, params = q.build()
        assert sql == (
            'WITH "recent_posts" AS ('
            'SELECT "posts"."user_id","posts"."title" FROM "public"."posts"'
            ') SELECT "users"."name","recent_posts"."title" FROM "public"."users"'
            ' JOIN "recent_posts" ON "users"."id"="recent_posts"."user_id"'
        )
        assert params == ()

    def test_cte_params_numbered_before_outer_params(self):
        recent_posts = Posts.select(Posts.user_id, Posts.title).where(Posts.id > 100).aliased("recent_posts")
        q = With(
            recent_posts,
            query=(
                Users.select(Users.name)
                .join(recent_posts, on=Users.id == recent_posts.user_id)
                .where(Users.name == "alice")
            ),
        )
        sql, params = q.build()
        assert sql == (
            'WITH "recent_posts" AS ('
            'SELECT "posts"."user_id","posts"."title" FROM "public"."posts" WHERE "posts"."id">$1'
            ') SELECT "users"."name" FROM "public"."users"'
            ' JOIN "recent_posts" ON "users"."id"="recent_posts"."user_id"'
            ' WHERE "users"."name"=$2'
        )
        assert params == (100, "alice")

    def test_left_join_with_named_cte(self):
        rev = (
            Orders.select(Orders.user_id, Orders.amount.sum().aliased("total"))
            .group_by(Orders.user_id)
            .aliased("rev")
        )
        q = With(
            rev,
            query=(
                Users.select(Users.name, rev.total)
                .left_join(rev, on=Users.id == rev.user_id)
            ),
        )
        sql, params = q.build()
        assert sql == (
            'WITH "rev" AS ('
            'SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id"'
            ') SELECT "users"."name","rev"."total" FROM "public"."users"'
            ' LEFT JOIN "rev" ON "users"."id"="rev"."user_id"'
        )
        assert params == ()

    def test_cte_column_in_outer_where(self):
        rev = (
            Orders.select(Orders.user_id, Orders.amount.sum().aliased("total"))
            .group_by(Orders.user_id)
            .aliased("rev")
        )
        q = With(
            rev,
            query=(
                Users.select(Users.name)
                .join(rev, on=Users.id == rev.user_id)
                .where(rev.total > 500)
            ),
        )
        sql, params = q.build()
        assert sql == (
            'WITH "rev" AS ('
            'SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id"'
            ') SELECT "users"."name" FROM "public"."users"'
            ' JOIN "rev" ON "users"."id"="rev"."user_id"'
            ' WHERE "rev"."total">$1'
        )
        assert params == (500,)

    def test_two_ctes_rendered_in_registration_order(self):
        cte1 = Posts.select(Posts.user_id, Posts.title).aliased("cte1")
        cte2 = Orders.select(Orders.user_id, Orders.amount).aliased("cte2")
        q = With(cte1, cte2, query=Users.select(Users.name))
        sql, params = q.build()
        assert sql == (
            'WITH "cte1" AS ('
            'SELECT "posts"."user_id","posts"."title" FROM "public"."posts"'
            '), "cte2" AS ('
            'SELECT "orders"."user_id","orders"."amount" FROM "public"."orders"'
            ') SELECT "users"."name" FROM "public"."users"'
        )
        assert params == ()


class TestRecursiveCTE:
    def test_recursive_cte_sql(self):
        anchor = (
            Employees.select(Employees.id, Employees.name, Employees.manager_id)
            .where(Employees.manager_id.isnull())
        )
        org_cte_ref = anchor.aliased("org_cte")
        step = (
            Employees.select(Employees.id, Employees.name, Employees.manager_id)
            .join(org_cte_ref, on=Employees.manager_id == org_cte_ref.id)
        )
        org_cte = anchor.union(step, all=True).aliased("org_cte")
        q = With(
            org_cte,
            query=Employees.select(Employees.id, Employees.name),
            recursive=True,
        )
        sql, params = q.build()
        assert sql == (
            'WITH RECURSIVE "org_cte" AS ('
            'SELECT "employees"."id","employees"."name","employees"."manager_id"'
            ' FROM "public"."employees" WHERE "employees"."manager_id" IS NULL'
            ' UNION ALL '
            'SELECT "employees"."id","employees"."name","employees"."manager_id"'
            ' FROM "public"."employees"'
            ' JOIN "org_cte" ON "employees"."manager_id"="org_cte"."id"'
            ') SELECT "employees"."id","employees"."name" FROM "public"."employees"'
        )
        assert params == ()
