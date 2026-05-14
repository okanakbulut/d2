
from typing import Any, TypeVar

import msgspec

from .dialect import Dialect, PostgresDialect
from .query import InsertQuery, QueryBuilder

AnyQuery = QueryBuilder | InsertQuery

T = TypeVar("T")


class AsyncConnection:
    def __init__(self, conn: Any, dialect: Dialect = PostgresDialect()) -> None:
        self._conn = conn
        self._dialect = dialect

    async def fetch(self, qb: QueryBuilder, result_type: type[T]) -> list[T]:
        sql, params = qb.build(self._dialect)
        rows = await self._conn.fetch(sql, *params)
        return [msgspec.convert(dict(row), result_type) for row in rows]

    async def fetch_one(self, qb: QueryBuilder, result_type: type[T]) -> T | None:
        sql, params = qb.build(self._dialect)
        row = await self._conn.fetchrow(sql, *params)
        if row is None:
            return None
        return msgspec.convert(dict(row), result_type)

    async def fetch_val(self, qb: QueryBuilder) -> Any:
        sql, params = qb.build(self._dialect)
        return await self._conn.fetchval(sql, *params)

    async def execute(self, qb: AnyQuery) -> Any:
        sql, params = qb.build(self._dialect)
        return await self._conn.execute(sql, *params)

    async def execute_many(self, qb: AnyQuery) -> Any:
        sql, params = qb.build(self._dialect)
        return await self._conn.executemany(sql, params)

    def transaction(self) -> Any:
        return self._conn.transaction()
