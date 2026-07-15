"""Unit tests for INSERT … ON CONFLICT (UPSERT) query building."""
from norm import excluded
from .conftest import Users


class TestDoNothing:
    def test_do_nothing_sql(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_nothing()
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO NOTHING'
        assert params == ("Alice", "a@x.com")


class TestExplicitDefaultedValues:
    def test_upsert_keeps_explicit_pk_value(self):
        sql, params = (
            Users.insert(id=99, name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_update(name=excluded(Users.name))
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("id","name","email") VALUES ($1,$2,$3) ON CONFLICT ("email") DO UPDATE SET "name"=EXCLUDED."name"'
        assert params == (99, "Alice", "a@x.com")


class TestDoUpdateExcluded:
    def test_do_update_with_excluded_reference(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_update(name=excluded(Users.name))
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "name"=EXCLUDED."name"'
        assert params == ("Alice", "a@x.com")


class TestDoUpdateLiteral:
    def test_do_update_with_literal_value(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_update(name="Updated")
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "name"=$3'
        assert params == ("Alice", "a@x.com", "Updated")


class TestDoUpdateArithmetic:
    def test_do_update_with_arithmetic_expression(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com", age=0)
            .on_conflict(Users.email)
            .do_update(age=Users.age + 1)
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email","age") VALUES ($1,$2,$3) ON CONFLICT ("email") DO UPDATE SET "age"="users"."age"+$4'
        assert params == ("Alice", "a@x.com", 0, 1)


class TestCompositeConflictTarget:
    def test_composite_conflict_target(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com", age=30)
            .on_conflict(Users.email, Users.age)
            .do_update(name=excluded(Users.name))
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email","age") VALUES ($1,$2,$3) ON CONFLICT ("email", "age") DO UPDATE SET "name"=EXCLUDED."name"'
        assert params == ("Alice", "a@x.com", 30)


class TestBulkInsertOnConflict:
    def test_bulk_do_update_excluded(self):
        sql, params = (
            Users.insert([
                {"name": "Alice", "email": "a@x.com"},
                {"name": "Bob",   "email": "b@x.com"},
            ])
            .on_conflict(Users.email)
            .do_update(name=excluded(Users.name))
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "name"=EXCLUDED."name"'
        assert params == [("Alice", "a@x.com"), ("Bob", "b@x.com")]

    def test_bulk_do_update_literal_appended_to_each_row(self):
        sql, params = (
            Users.insert([
                {"name": "Alice", "email": "a@x.com"},
                {"name": "Bob",   "email": "b@x.com"},
            ])
            .on_conflict(Users.email)
            .do_update(name="Replaced")
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "name"=$3'
        assert params == [("Alice", "a@x.com", "Replaced"), ("Bob", "b@x.com", "Replaced")]

    def test_bulk_do_nothing(self):
        sql, params = (
            Users.insert([
                {"name": "Alice", "email": "a@x.com"},
                {"name": "Bob",   "email": "b@x.com"},
            ])
            .on_conflict(Users.email)
            .do_nothing()
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO NOTHING'
        assert params == [("Alice", "a@x.com"), ("Bob", "b@x.com")]


class TestReturning:
    def test_do_update_returning(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_update(name=excluded(Users.name))
            .returning(Users.id)
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "name"=EXCLUDED."name" RETURNING "users"."id"'
        assert params == ("Alice", "a@x.com")

    def test_do_nothing_returning(self):
        sql, params = (
            Users.insert(name="Alice", email="a@x.com")
            .on_conflict(Users.email)
            .do_nothing()
            .returning(Users.id, Users.name)
            .build()
        )
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) ON CONFLICT ("email") DO NOTHING RETURNING "users"."id","users"."name"'
        assert params == ("Alice", "a@x.com")
