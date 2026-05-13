
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pypika

from .dialect import Dialect, PostgresDialect

if TYPE_CHECKING:
    from .filter import Filter


@dataclass(frozen=True)
class QueryBuilder:
    source: pypika.Table
    columns: tuple[pypika.Field, ...]
    filters: tuple["Filter", ...] = ()

    def where(self, filter: "Filter") -> "QueryBuilder":
        return QueryBuilder(
            source=self.source,
            columns=self.columns,
            filters=self.filters + (filter,),
        )

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        q = pypika.Query.from_(self.source).select(*self.columns)
        for filter in self.filters:
            q = q.where(filter.to_pypika(params, dialect))
        return q.get_sql(quote_char='"'), tuple(params)
