
from typing import Any, TypeVar

import msgspec

from .dialect import Dialect, PostgresDialect
from .query import QueryBuilder

T = TypeVar("T")


class AsyncConnection:
    def __init__(self, conn: Any, dialect: Dialect = PostgresDialect()) -> None:
        self._conn = conn
        self._dialect = dialect

    async def fetch(self, qb: QueryBuilder, result_type: type[T]) -> list[T]:
        sql, params = qb.build(self._dialect)
        rows = await self._conn.fetch(sql, *params)
        return [msgspec.convert(dict(row), result_type) for row in rows]
