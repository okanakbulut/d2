"""Unit tests for AsyncConnection against a fake asyncpg driver."""

import asyncio

import msgspec
import pytest

from norm import AsyncConnection
from .conftest import Users


class UserResult(msgspec.Struct):
    id: int
    name: str
    email: str


class FakeRow:
    def __init__(self, data: dict) -> None:
        self._data = data

    def __iter__(self):
        return iter(self._data.items())


class FakeConn:
    def __init__(self, fetchrow_result=None, fetchval_result=None, execute_result=""):
        self._fetchrow_result = fetchrow_result
        self._fetchval_result = fetchval_result
        self._execute_result = execute_result
        self.fetchrow_calls: list = []
        self.fetchval_calls: list = []
        self.execute_calls: list = []
        self.executemany_calls: list = []

    async def fetchrow(self, sql, *params):
        self.fetchrow_calls.append((sql, params))
        return self._fetchrow_result

    async def fetchval(self, sql, *params):
        self.fetchval_calls.append((sql, params))
        return self._fetchval_result

    async def execute(self, sql, *params):
        self.execute_calls.append((sql, params))
        return self._execute_result

    async def executemany(self, sql, args):
        self.executemany_calls.append((sql, args))

    def transaction(self):
        return self._txn

    class _txn:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass


class TestFetchOne:
    def test_returns_struct_when_row_exists(self):
        row = FakeRow({"id": 1, "name": "Alice", "email": "a@x.com"})
        conn = AsyncConnection(FakeConn(fetchrow_result=row))
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 1)
        result = asyncio.run(conn.fetch_one(q, UserResult))
        assert result is not None
        assert result.name == "Alice"

    def test_returns_none_when_no_row(self):
        conn = AsyncConnection(FakeConn(fetchrow_result=None))
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 99)
        assert asyncio.run(conn.fetch_one(q, UserResult)) is None

    def test_calls_fetchrow_with_correct_sql_and_params(self):
        fake = FakeConn(fetchrow_result=None)
        conn = AsyncConnection(fake)
        q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 7)
        asyncio.run(conn.fetch_one(q, UserResult))
        assert len(fake.fetchrow_calls) == 1
        sql, params = fake.fetchrow_calls[0]
        assert sql == 'SELECT "users"."id","users"."name","users"."email" FROM "public"."users" WHERE "users"."id"=$1'
        assert params == (7,)


class TestFetchVal:
    def test_returns_scalar(self):
        conn = AsyncConnection(FakeConn(fetchval_result=42))
        result = asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        assert result == 42

    def test_returns_none_when_no_row(self):
        conn = AsyncConnection(FakeConn(fetchval_result=None))
        result = asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        assert result is None

    def test_calls_fetchval_with_correct_args(self):
        fake = FakeConn(fetchval_result=None)
        conn = AsyncConnection(fake)
        asyncio.run(conn.fetch_val(Users.select(Users.id).where(Users.age >= 18)))
        assert len(fake.fetchval_calls) == 1
        sql, params = fake.fetchval_calls[0]
        assert sql == 'SELECT "users"."id" FROM "public"."users" WHERE "users"."age">=$1'
        assert params == (18,)


class TestExecute:
    def test_returns_driver_status(self):
        conn = AsyncConnection(FakeConn(execute_result="INSERT 0 1"))
        status = asyncio.run(conn.execute(Users.insert({"name": "Alice", "email": "a@x.com"})))
        assert status == "INSERT 0 1"

    def test_calls_driver_with_correct_sql_and_params(self):
        fake = FakeConn(execute_result="INSERT 0 1")
        conn = AsyncConnection(fake)
        asyncio.run(conn.execute(Users.insert({"name": "Alice", "email": "a@x.com"})))
        assert len(fake.execute_calls) == 1
        sql, params = fake.execute_calls[0]
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert params == ("Alice", "a@x.com")


class TestExecuteMany:
    def test_calls_executemany_with_param_list(self):
        fake = FakeConn()
        conn = AsyncConnection(fake)
        q = Users.insert([
            {"name": "Alice", "email": "a@x.com"},
            {"name": "Bob",   "email": "b@x.com"},
        ])
        asyncio.run(conn.execute_many(q))
        assert len(fake.executemany_calls) == 1
        sql, args = fake.executemany_calls[0]
        assert sql == 'INSERT INTO "public"."users" ("name","email") VALUES ($1,$2)'
        assert args == [("Alice", "a@x.com"), ("Bob", "b@x.com")]


class TestTransaction:
    def test_returns_driver_context_manager(self):
        fake = FakeConn()
        conn = AsyncConnection(fake)
        assert conn.transaction() is FakeConn._txn
