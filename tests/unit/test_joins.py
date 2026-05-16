"""Unit tests for JOIN support and table aliasing."""

from .conftest import Users, Posts, Employees


class TestInnerJoin:
    def test_inner_join_sql(self):
        sql, params = (
            Users.select(Users.id, Posts.title)
            .join(Posts, on=Users.id == Posts.user_id)
            .build()
        )
        assert sql == (
            'SELECT "users"."id","posts"."title" FROM "public"."users"'
            ' JOIN "public"."posts" ON "users"."id"="posts"."user_id"'
        )
        assert params == ()


class TestLeftJoin:
    def test_left_join_sql(self):
        sql, params = (
            Users.select(Users.id, Posts.title)
            .left_join(Posts, on=Users.id == Posts.user_id)
            .build()
        )
        assert sql == (
            'SELECT "users"."id","posts"."title" FROM "public"."users"'
            ' LEFT JOIN "public"."posts" ON "users"."id"="posts"."user_id"'
        )
        assert params == ()


class TestRightJoin:
    def test_right_join_sql(self):
        sql, params = (
            Users.select(Users.id, Posts.title)
            .right_join(Posts, on=Users.id == Posts.user_id)
            .build()
        )
        assert sql == (
            'SELECT "users"."id","posts"."title" FROM "public"."users"'
            ' RIGHT JOIN "public"."posts" ON "users"."id"="posts"."user_id"'
        )
        assert params == ()


class TestCrossJoin:
    def test_cross_join_sql(self):
        sql, params = (
            Users.select(Users.id, Posts.id)
            .cross_join(Posts)
            .build()
        )
        assert sql == (
            'SELECT "users"."id","posts"."id" FROM "public"."users"'
            ' CROSS JOIN "public"."posts"'
        )
        assert params == ()


class TestTableAlias:
    def test_aliased_field_renders_alias_prefix(self):
        Mgr = Employees.aliased("mgr")
        sql, params = Mgr.select(Mgr.name).build()
        assert sql == 'SELECT "mgr"."name" FROM "public"."employees" "mgr"'
        assert params == ()

    def test_two_alias_calls_same_alias_equivalent(self):
        A = Employees.aliased("e")
        B = Employees.aliased("e")
        sql_a, _ = A.select(A.id).build()
        sql_b, _ = B.select(B.id).build()
        assert sql_a == sql_b


class TestSelfJoin:
    def test_self_join_sql(self):
        Mgr = Employees.aliased("mgr")
        Rep = Employees.aliased("rep")
        sql, params = (
            Mgr.select(Mgr.name, Rep.name)
            .join(Rep, on=Mgr.id == Rep.manager_id)
            .build()
        )
        assert sql == (
            'SELECT "mgr"."name","rep"."name" FROM "public"."employees" "mgr"'
            ' JOIN "public"."employees" "rep" ON "mgr"."id"="rep"."manager_id"'
        )
        assert params == ()


class TestCompoundCriterion:
    def test_and_criterion_in_join(self):
        Mgr = Employees.aliased("mgr")
        Rep = Employees.aliased("rep")
        criterion = (Mgr.id == Rep.manager_id) & (Rep.name == "Alice")
        sql, params = (
            Mgr.select(Mgr.name, Rep.name)
            .join(Rep, on=criterion)
            .build()
        )
        assert sql == (
            'SELECT "mgr"."name","rep"."name" FROM "public"."employees" "mgr"'
            ' JOIN "public"."employees" "rep"'
            ' ON "mgr"."id"="rep"."manager_id" AND "rep"."name"=$1'
        )
        assert params == ("Alice",)
