
import typing
from typing import Any, TypeVar, overload

import msgspec

from .dialect import Dialect, PostgresDialect
from .query import InsertQuery, QueryBuilder, UpdateQuery, DeleteQuery, With

AnyQuery = QueryBuilder | InsertQuery | UpdateQuery | DeleteQuery | With

T = TypeVar("T")


class AsyncConnection:
    def __init__(self, conn: Any, dialect: Dialect = PostgresDialect()) -> None:
        self._conn = conn
        self._dialect = dialect

    @overload
    async def fetch(self, qb: AnyQuery, result_type: type[list[T]]) -> list[T]: ...
    @overload
    async def fetch(self, qb: AnyQuery, result_type: type[T]) -> T | None: ...

    async def fetch(self, qb: AnyQuery, result_type: Any) -> Any:
        sql, params = qb.build(self._dialect)
        if typing.get_origin(result_type) is list:
            item_type = typing.get_args(result_type)[0]
            rows = await self._conn.fetch(sql, *params)
            return [msgspec.convert(dict(row), item_type) for row in rows]
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
