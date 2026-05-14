
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any

import pypika
import pypika.enums
import pypika.terms

from .dialect import Dialect, PostgresDialect

if TYPE_CHECKING:
    from .filter import Filter
    from .schema import Field as NormField


@dataclass(frozen=True)
class InsertQuery:
    source: pypika.Table
    rows: tuple[dict[str, Any], ...]

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, Any]:
        if not self.rows:
            raise ValueError("insert requires at least one row")
        columns = list(self.rows[0].keys())
        placeholders = [
            pypika.terms.Parameter(dialect.placeholder(i + 1))
            for i in range(len(columns))
        ]
        q = pypika.Query.into(self.source).columns(*columns).insert(*placeholders)
        sql = q.get_sql(quote_char='"')
        if len(self.rows) == 1:
            return sql, tuple(self.rows[0][col] for col in columns)
        return sql, [tuple(row[col] for col in columns) for row in self.rows]


@dataclass(frozen=True)
class QueryBuilder:
    source: pypika.Table
    columns: "tuple[NormField[Any], ...]"
    filters: "tuple[Filter, ...]" = dc_field(default_factory=tuple)
    orderings: "tuple[tuple[NormField[Any], bool], ...]" = dc_field(default_factory=tuple)
    row_limit: int | None = None
    row_offset: int | None = None
    is_distinct: bool = False

    def where(self, filter: "Filter") -> "QueryBuilder":
        return QueryBuilder(
            source=self.source, columns=self.columns,
            filters=self.filters + (filter,),
            orderings=self.orderings, row_limit=self.row_limit,
            row_offset=self.row_offset, is_distinct=self.is_distinct,
        )

    def order_by(self, *fields: "NormField[Any]", desc: bool = False) -> "QueryBuilder":
        new_orderings = self.orderings + tuple((f, desc) for f in fields)
        return QueryBuilder(
            source=self.source, columns=self.columns, filters=self.filters,
            orderings=new_orderings, row_limit=self.row_limit,
            row_offset=self.row_offset, is_distinct=self.is_distinct,
        )

    def limit(self, n: int) -> "QueryBuilder":
        return QueryBuilder(
            source=self.source, columns=self.columns, filters=self.filters,
            orderings=self.orderings, row_limit=n,
            row_offset=self.row_offset, is_distinct=self.is_distinct,
        )

    def offset(self, n: int) -> "QueryBuilder":
        return QueryBuilder(
            source=self.source, columns=self.columns, filters=self.filters,
            orderings=self.orderings, row_limit=self.row_limit,
            row_offset=n, is_distinct=self.is_distinct,
        )

    def distinct(self) -> "QueryBuilder":
        return QueryBuilder(
            source=self.source, columns=self.columns, filters=self.filters,
            orderings=self.orderings, row_limit=self.row_limit,
            row_offset=self.row_offset, is_distinct=True,
        )

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        pika_cols = [col.to_column(params, dialect) for col in self.columns]
        q = pypika.Query.from_(self.source).select(*pika_cols)
        if self.is_distinct:
            q = q.distinct()
        for f in self.filters:
            q = q.where(f.to_pypika(params, dialect))
        for field, is_desc in self.orderings:
            order = pypika.enums.Order.desc if is_desc else pypika.enums.Order.asc
            q = q.orderby(field.pika_field, order=order)
        if self.row_limit is not None:
            q = q.limit(self.row_limit)
        if self.row_offset is not None:
            q = q.offset(self.row_offset)
        return q.get_sql(quote_char='"'), tuple(params)
