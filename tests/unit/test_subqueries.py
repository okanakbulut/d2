"""Unit tests for QueryBuilder.as_view() and QueryBuilder.as_scalar()."""

import pytest

from norm.query import ScalarSubquery, SubqueryProxy
from norm.schema import Field
from .conftest import Users, Orders


class TestAsView:
    def test_as_view_returns_subquery_proxy(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        assert isinstance(view, SubqueryProxy)

    def test_as_view_exposes_plain_column_as_field(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        assert isinstance(view.user_id, Field)  

    def test_as_view_exposes_aliased_agg_as_field(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        assert isinstance(view.total, Field)

    def test_as_view_does_not_expose_unnamed_agg(self):
        inner = Orders.select(Orders.amount.sum())  # no alias
        view = inner.as_view("rev")
        assert not hasattr(view, "")


class TestSubqueryProxyImmutability:
    def test_raises_on_attribute_set(self):
        view = Orders.select(Orders.user_id).as_view("rev")
        with pytest.raises(AttributeError):
            view.user_id = None

    def test_raises_on_new_attribute(self):
        view = Orders.select(Orders.user_id).as_view("rev")
        with pytest.raises(AttributeError):
            view.foo = "bar"


class TestSubqueryJoin:
    def test_join_renders_full_subquery_sql(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        q = Users.select(Users.name).join(view, on=Users.id == view.user_id)
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."name" FROM "public"."users"'
            ' JOIN (SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id") "rev"'
            ' ON "users"."id"="rev"."user_id"'
        )
        assert params == ()

    def test_left_join_subquery(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        q = Users.select(Users.name).left_join(view, on=Users.id == view.user_id)
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."name" FROM "public"."users"'
            ' LEFT JOIN (SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id") "rev"'
            ' ON "users"."id"="rev"."user_id"'
        )
        assert params == ()

    def test_subquery_column_in_outer_where(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        q = (Users.select(Users.name)
             .join(view, on=Users.id == view.user_id)
             .where(view.total > 1000))
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."name" FROM "public"."users"'
            ' JOIN (SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id") "rev"'
            ' ON "users"."id"="rev"."user_id"'
            ' WHERE "rev"."total">$1'
        )
        assert params == (1000,)

    def test_subquery_column_in_outer_select(self):
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id)
        view = inner.as_view("rev")
        q = (Users.select(Users.name, view.total)
             .join(view, on=Users.id == view.user_id))
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."name","rev"."total" FROM "public"."users"'
            ' JOIN (SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id") "rev"'
            ' ON "users"."id"="rev"."user_id"'
        )
        assert params == ()

    def test_inner_subquery_params_numbered_before_outer(self):
        # Inner query has a WHERE param; outer query also has one.
        inner = Orders.select(Orders.user_id, Orders.amount.sum().as_("total")).group_by(Orders.user_id).having(Orders.amount.sum() > 50)
        view = inner.as_view("rev")
        q = (Users.select(Users.name)
             .join(view, on=Users.id == view.user_id)
             .where(Users.name == "alice"))
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."name" FROM "public"."users"'
            ' JOIN (SELECT "orders"."user_id",SUM("orders"."amount") "total"'
            ' FROM "public"."orders" GROUP BY "orders"."user_id"'
            ' HAVING SUM("orders"."amount")>$1) "rev"'
            ' ON "users"."id"="rev"."user_id"'
            ' WHERE "users"."name"=$2'
        )
        assert params == (50, "alice")


class TestAsScalar:
    def test_as_scalar_returns_scalar_subquery(self):
        qb = Users.select(Users.age.avg())
        assert isinstance(qb.as_scalar(), ScalarSubquery)

    def test_scalar_subquery_in_where_no_inner_params(self):
        avg_age_qb = Users.select(Users.age.avg())
        q = Users.select(Users.id).where(Users.age > avg_age_qb.as_scalar())
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id" FROM "public"."users"'
            ' WHERE "users"."age">(SELECT AVG("users"."age") FROM "public"."users")'
        )
        assert params == ()

    def test_scalar_subquery_params_flow_to_outer(self):
        # Inner query has a bound param; outer query also has a bound param.
        # Inner params must be numbered before outer params.
        inner = Users.select(Users.age.avg()).where(Users.id > 0)
        q = Users.select(Users.id).where(Users.age > inner.as_scalar()).where(Users.name == "alice")
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id" FROM "public"."users"'
            ' WHERE "users"."age">(SELECT AVG("users"."age") FROM "public"."users" WHERE "users"."id">$1)'
            ' AND "users"."name"=$2'
        )
        assert params == (0, "alice")
