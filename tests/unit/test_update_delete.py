"""Unit tests for UpdateQuery and DeleteQuery."""

from .conftest import Users


class TestUpdate:
    def test_update_literal_set(self):
        sql, params = Users.update(name="Veteran").build()
        assert sql == 'UPDATE "public"."users" SET "name"=$1'
        assert params == ("Veteran",)

    def test_update_arithmetic_set(self):
        sql, params = Users.update(age=Users.age + 1).build()
        assert sql == 'UPDATE "public"."users" SET "age"="users"."age"+$1'
        assert params == (1,)

    def test_update_multi_column_set(self):
        sql, params = Users.update(age=Users.age + 1, name="Veteran").build()
        assert sql == 'UPDATE "public"."users" SET "age"="users"."age"+$1,"name"=$2'
        assert params == (1, "Veteran")

    def test_update_with_where(self):
        sql, params = Users.update(name="Veteran").where(Users.age >= 65).build()
        assert sql == 'UPDATE "public"."users" SET "name"=$1 WHERE "users"."age">=$2'
        assert params == ("Veteran", 65)

    def test_update_where_returns_new_instance(self):
        base = Users.update(name="X")
        filtered = base.where(Users.id == 1)
        assert base is not filtered
        sql, params = base.build()
        assert sql == 'UPDATE "public"."users" SET "name"=$1'
        assert params == ("X",)


class TestDelete:
    def test_delete_no_where(self):
        sql, params = Users.delete().build()
        assert sql == 'DELETE FROM "public"."users"'
        assert params == ()

    def test_delete_with_where(self):
        sql, params = Users.delete().where(Users.id == 42).build()
        assert sql == 'DELETE FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (42,)

    def test_delete_where_returns_new_instance(self):
        base = Users.delete()
        filtered = base.where(Users.id == 1)
        assert base is not filtered
        sql, params = base.build()
        assert sql == 'DELETE FROM "public"."users"'
        assert params == ()
