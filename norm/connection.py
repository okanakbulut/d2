
import json
import typing
from typing import Any, TypeVar, overload

import msgspec

from .dialect import Dialect, PostgresDialect

T = TypeVar("T")

# AnyQuery covers Entity clone types (with .build() classmethod) and the mutable query objects
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

    async def fetch_val(self, qb: AnyQuery) -> Any:
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

    # --- Migration-runner accessors -------------------------------------------------
    # These wrap raw asyncpg calls without going through the query builder; they are
    # intended for the migration system (DDL + tracking-table maintenance) which
    # needs to execute literal SQL strings against the underlying driver.

    async def raw_execute(self, sql: str, *args: Any) -> Any:
        """Execute a raw SQL string against the underlying driver."""
        return await self._conn.execute(sql, *args)

    async def raw_fetch(self, sql: str, *args: Any) -> list[Any]:
        """Run a raw SQL query and return the rows from the underlying driver."""
        rows: Any = await self._conn.fetch(sql, *args)
        return list(rows)

    def raw_transaction(self) -> Any:
        """Return the underlying driver's transaction context manager."""
        return self._conn.transaction()
