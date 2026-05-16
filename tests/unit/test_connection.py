"""Unit tests for AsyncConnection against a mock asyncpg driver."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import msgspec

from norm import AsyncConnection
from .conftest import Users


class UserResult(msgspec.Struct):
    id: int
    name: str
    email: str


class TestFetch:
    def test_single_returns_struct_when_row_exists(self):
        driver = MagicMock()
        driver.fetchrow = AsyncMock(return_value={"id": 1, "name": "Alice", "email": "a@x.com"})
        conn = AsyncConnection(driver)
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 1)
        result = asyncio.run(conn.fetch(q, UserResult))
        assert result is not None
        assert result.name == "Alice"

    def test_single_returns_none_when_no_row(self):
        driver = MagicMock()
        driver.fetchrow = AsyncMock(return_value=None)
        conn = AsyncConnection(driver)
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 99)
        assert asyncio.run(conn.fetch(q, UserResult)) is None

    def test_single_calls_fetchrow_with_correct_sql_and_params(self):
        driver = MagicMock()
        driver.fetchrow = AsyncMock(return_value=None)
        conn = AsyncConnection(driver)
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 7)
        asyncio.run(conn.fetch(q, UserResult))
        driver.fetchrow.assert_called_once_with(
            'SELECT "users"."id","users"."name","users"."email" FROM "public"."users" WHERE "users"."id"=$1',
            7,
        )

    def test_many_returns_list_of_structs(self):
        rows: list[dict[str, object]] = [
            {"id": 1, "name": "Alice", "email": "a@x.com"},
            {"id": 2, "name": "Bob",   "email": "b@x.com"},
        ]
        driver = MagicMock()
        driver.fetch = AsyncMock(return_value=rows)
        conn = AsyncConnection(driver)
        q = Users.select(Users.id, Users.name, Users.email)
        results = asyncio.run(conn.fetch(q, list[UserResult]))
        assert len(results) == 2
        assert results[0].name == "Alice"
        assert results[1].name == "Bob"

    def test_many_calls_fetch_with_correct_sql(self):
        driver = MagicMock()
        driver.fetch = AsyncMock(return_value=[])
        conn = AsyncConnection(driver)
        q = Users.select(Users.id, Users.name, Users.email).where(Users.age >= 18)
        asyncio.run(conn.fetch(q, list[UserResult]))
        driver.fetch.assert_called_once_with(
            'SELECT "users"."id","users"."name","users"."email" FROM "public"."users" WHERE "users"."age">=$1',
            18,
        )


class TestFetchVal:
    def test_returns_scalar(self):
        driver = MagicMock()
        driver.fetchval = AsyncMock(return_value=42)
        conn = AsyncConnection(driver)
        result = asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        assert result == 42

    def test_returns_none_when_no_row(self):
        driver = MagicMock()
        driver.fetchval = AsyncMock(return_value=None)
        conn = AsyncConnection(driver)
        result = asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        assert result is None

    def test_calls_fetchval_with_correct_args(self):
        driver = MagicMock()
        driver.fetchval = AsyncMock(return_value=None)
        conn = AsyncConnection(driver)
        asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        driver.fetchval.assert_called_once_with(
            'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">=$1',
            18,
        )


class TestExecute:
    def test_returns_driver_status(self):
        driver = MagicMock()
        driver.execute = AsyncMock(return_value="INSERT 0 1")
        conn = AsyncConnection(driver)
        status = asyncio.run(conn.execute(Users.insert(name="Alice", email="a@x.com")))
        assert status == "INSERT 0 1"

    def test_calls_driver_with_correct_sql_and_params(self):
        driver = MagicMock()
        driver.execute = AsyncMock(return_value="INSERT 0 1")
        conn = AsyncConnection(driver)
        asyncio.run(conn.execute(Users.insert(name="Alice", email="a@x.com")))
        driver.execute.assert_called_once_with(
            'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)',
            "Alice", "a@x.com",
        )


class TestExecuteMany:
    def test_calls_executemany_with_param_list(self):
        driver = MagicMock()
        driver.executemany = AsyncMock()
        conn = AsyncConnection(driver)
        q = Users.insert([
            {"name": "Alice", "email": "a@x.com"},
            {"name": "Bob",   "email": "b@x.com"},
        ])
        asyncio.run(conn.execute_many(q))
        driver.executemany.assert_called_once_with(
            'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)',
            [("Alice", "a@x.com"), ("Bob", "b@x.com")],
        )


class TestTransaction:
    def test_returns_driver_context_manager(self):
        driver = MagicMock()
        conn = AsyncConnection(driver)
        assert conn.transaction() is driver.transaction()
