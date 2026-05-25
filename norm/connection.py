import json
import typing
from typing import Any, TypeVar, overload

import msgspec

from .dialect import Dialect, PostgresDialect
from .driver import Driver

T = TypeVar("T")

AnyQuery = Any


class AsyncConnection:
    def __init__(self, conn: Any, dialect: Dialect = PostgresDialect()) -> None:
        self._conn = conn
        self._dialect = dialect
        self._json_codec_registered = False

    async def _ensure_json_codec(self) -> None:
        if not self._json_codec_registered:
            await self._conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
            self._json_codec_registered = True

    @overload
    async def fetch(self, qb: AnyQuery, result_type: type[list[T]]) -> list[T]: ...
    @overload
    async def fetch(self, qb: AnyQuery, result_type: type[T]) -> T | None: ...

    async def fetch(self, qb: AnyQuery, result_type: Any) -> Any:
        await self._ensure_json_codec()
        sql, params = qb.build(self._dialect)
        if getattr(qb, '__as_json__', None) is not None:
            val = await self._conn.fetchval(sql, *params)
            if val is None:
                return None
            data = json.loads(val) if isinstance(val, str) else val
            return msgspec.convert(data, result_type)
        if typing.get_origin(result_type) is list:
            item_type = typing.get_args(result_type)[0]
            rows = await self._conn.fetch(sql, *params)
            return [msgspec.convert(dict(row), item_type) for row in rows]
        row = await self._conn.fetchrow(sql, *params)
        if row is None:
            return None
        return msgspec.convert(dict(row), result_type)

    async def fetchval(self, qb: AnyQuery) -> Any:
        await self._ensure_json_codec()
        sql, params = qb.build(self._dialect)
        val = await self._conn.fetchval(sql, *params)
        if getattr(qb, '__as_json__', None) is not None and isinstance(val, dict):
            return json.dumps(val)
        return val

    async def execute(self, qb: AnyQuery) -> Any:
        sql, params = qb.build(self._dialect)
        return await self._conn.execute(sql, *params)

    async def execute_many(self, qb: AnyQuery) -> Any:
        sql, params = qb.build(self._dialect)
        return await self._conn.executemany(sql, params)

    def transaction(self) -> Any:
        return self._conn.transaction()

    async def raw_execute(self, sql: str, *args: Any) -> Any:
        return await self._conn.execute(sql, *args)

    async def raw_fetch(self, sql: str, *args: Any) -> list[Any]:
        rows: Any = await self._conn.fetch(sql, *args)
        return list(rows)

    def raw_transaction(self) -> Any:
        return self._conn.transaction()


class AsyncpgDriver:
    """Implements Driver over a raw asyncpg connection.

    execute() uses asyncpg.fetch so it returns rows for SELECT and an empty
    list for DDL/DML — the migration runner ignores the return for non-SELECT.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute(self, query: str, *args: Any) -> list[Any]:
        rows: Any = await self._conn.fetch(query, *args)
        return list(rows)

    def transaction(self) -> Any:
        return self._conn.transaction()


_: type[Driver] = AsyncpgDriver  # static assert AsyncpgDriver satisfies Driver
