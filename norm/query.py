
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any

import pypika
import pypika.enums
import pypika.terms

from .dialect import Dialect, PostgresDialect

if TYPE_CHECKING:
    from .filter import Filter, AnyFilter
    from .schema import Entity, Field as NormField


@dataclass(frozen=True)
class ScalarSubquery:
    inner: "QueryBuilder"


class SubqueryProxy:
    """Named inline view: wraps a QueryBuilder or UnionQuery with an alias and exposes projected columns as Field attributes."""

    inner: "QueryBuilder | UnionQuery"
    alias: str
    __table__: pypika.Table

    def __init__(self, inner: "QueryBuilder | UnionQuery", alias: str) -> None:
        from .schema import Field as NormField, NamespacedField
        object.__setattr__(self, "inner", inner)
        object.__setattr__(self, "alias", alias)
        alias_table = pypika.Table(alias)
        object.__setattr__(self, "__table__", alias_table)
        source = inner.left if isinstance(inner, UnionQuery) else inner
        for col in source.columns:
            name = getattr(col.pika_field, "alias", None) or col.column_name
            if not name:
                continue
            pika = NamespacedField(name, table=alias_table)
            proxy = NormField(name, col.python_type, col.field_def, pika)
            object.__setattr__(self, name, proxy)

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: ARG002
        raise AttributeError(f"cannot set '{name}' on SubqueryProxy")

    def __getattr__(self, name: str) -> "NormField[Any]":
        raise AttributeError(f"'{self.alias}' has no column '{name}'")


@dataclass(frozen=True)
class UnionQuery:
    left: "QueryBuilder"
    right: "QueryBuilder"
    all: bool = False

    def as_view(self, alias: str) -> "SubqueryProxy":
        return SubqueryProxy(self, alias)

    def as_pypika(self, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        left_pika = self.left.as_pypika(params, dialect, cte_names)
        right_pika = self.right.as_pypika(params, dialect, cte_names)
        if self.all:
            return left_pika.union_all(right_pika)
        return left_pika.union(right_pika)


@dataclass(frozen=True)
class JoinClause:
    table: Any  # pypika.Table for model joins, SubqueryProxy for subquery joins
    criterion: "AnyFilter | None"
    kind: str  # "inner" | "left" | "right" | "cross"

    def apply_to(self, q: Any, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        if isinstance(self.table, SubqueryProxy) and self.table.alias not in cte_names:
            from pypika.queries import JoinOn, Join as PikaJoin
            inner_pika = self.table.inner.as_pypika(params, dialect)
            join_target = inner_pika.as_(self.table.alias)
            join_type_map = {
                "inner": pypika.enums.JoinType.inner,
                "left": pypika.enums.JoinType.left,
                "right": pypika.enums.JoinType.right,
            }
            if self.kind == "cross":
                q._joins.append(PikaJoin(join_target, pypika.enums.JoinType.cross))  # type: ignore[attr-defined]
            else:
                criterion_pika = self.criterion.to_pypika(params, dialect)  # type: ignore[union-attr]
                q._joins.append(JoinOn(join_target, join_type_map[self.kind], criterion_pika, None))  # type: ignore[arg-type, attr-defined]
            return q
        pika_table = pypika.Table(self.table.alias) if isinstance(self.table, SubqueryProxy) else self.table
        if self.kind == "inner":
            return q.join(pika_table).on(self.criterion.to_pypika(params, dialect))  # type: ignore[union-attr]
        elif self.kind == "left":
            return q.left_join(pika_table).on(self.criterion.to_pypika(params, dialect))  # type: ignore[union-attr]
        elif self.kind == "right":
            return q.right_join(pika_table).on(self.criterion.to_pypika(params, dialect))  # type: ignore[union-attr]
        elif self.kind == "cross":
            return q.join(pika_table, pypika.enums.JoinType.cross).cross()
        return q


@dataclass(frozen=True)
class InsertQuery:
    source: pypika.Table
    rows: tuple[dict[str, Any], ...]
    is_many: bool = False
    returning_fields: "tuple[NormField[Any], ...]" = dc_field(default_factory=tuple)

    def returning(self, *fields: "NormField[Any]") -> "InsertQuery":
        return InsertQuery(
            source=self.source, rows=self.rows,
            is_many=self.is_many, returning_fields=fields,
        )

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
        if self.returning_fields:
            ret_cols = ",".join(f.pika_field.get_sql(quote_char='"') for f in self.returning_fields)
            sql = f"{sql} RETURNING {ret_cols}"
        if self.is_many:
            return sql, [tuple(row[col] for col in columns) for row in self.rows]
        return sql, tuple(self.rows[0][col] for col in columns)


@dataclass(frozen=True)
class UpdateQuery:
    source: pypika.Table
    assignments: "tuple[tuple[str, Any], ...]"
    filters: "tuple[Filter, ...]" = dc_field(default_factory=tuple)

    def where(self, filter: "Filter") -> "UpdateQuery":
        return UpdateQuery(
            source=self.source, assignments=self.assignments,
            filters=self.filters + (filter,),
        )

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        q = pypika.Query.update(self.source) # type: ignore[no-untyped-call]
        for col_name, value in self.assignments:
            from .schema import Field as NormField
            if isinstance(value, NormField):
                val_term = value.to_column(params, dialect)
                q = q.set(pypika.Field(col_name), val_term)
            else:
                params.append(value)
                q = q.set(pypika.Field(col_name), pypika.terms.Parameter(dialect.placeholder(len(params))))
        for f in self.filters:
            q = q.where(f.to_pypika(params, dialect))
        return q.get_sql(quote_char='"'), tuple(params)


@dataclass(frozen=True)
class DeleteQuery:
    source: pypika.Table
    filters: "tuple[Filter, ...]" = dc_field(default_factory=tuple)

    def where(self, filter: "Filter") -> "DeleteQuery":
        return DeleteQuery(
            source=self.source,
            filters=self.filters + (filter,),
        )

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        q = pypika.Query.from_(self.source).delete()
        for f in self.filters:
            q = q.where(f.to_pypika(params, dialect))
        return q.get_sql(quote_char='"'), tuple(params)


@dataclass(frozen=True)
class QueryBuilder:
    source: pypika.Table
    columns: "tuple[NormField[Any], ...]"
    filters: "tuple[Filter, ...]" = dc_field(default_factory=tuple)
    orderings: "tuple[tuple[NormField[Any], bool], ...]" = dc_field(default_factory=tuple)
    row_limit: int | None = None
    row_offset: int | None = None
    is_distinct: bool = False
    joins: tuple[JoinClause, ...] = dc_field(default_factory=tuple)
    group_bys: "tuple[NormField[Any], ...]" = dc_field(default_factory=tuple)
    havings: "tuple[Filter | AnyFilter, ...]" = dc_field(default_factory=tuple)

    def _copy(self, **overrides: Any) -> "QueryBuilder":
        return QueryBuilder(
            source=overrides.get("source", self.source),
            columns=overrides.get("columns", self.columns),
            filters=overrides.get("filters", self.filters),
            orderings=overrides.get("orderings", self.orderings),
            row_limit=overrides.get("row_limit", self.row_limit),
            row_offset=overrides.get("row_offset", self.row_offset),
            is_distinct=overrides.get("is_distinct", self.is_distinct),
            joins=overrides.get("joins", self.joins),
            group_bys=overrides.get("group_bys", self.group_bys),
            havings=overrides.get("havings", self.havings),
        )

    def where(self, filter: "Filter") -> "QueryBuilder":
        return self._copy(filters=self.filters + (filter,))

    def order_by(self, *fields: "NormField[Any]", desc: bool = False) -> "QueryBuilder":
        return self._copy(orderings=self.orderings + tuple((f, desc) for f in fields))

    def limit(self, n: int) -> "QueryBuilder":
        return self._copy(row_limit=n)

    def offset(self, n: int) -> "QueryBuilder":
        return self._copy(row_offset=n)

    def distinct(self) -> "QueryBuilder":
        return self._copy(is_distinct=True)

    def join(self, other: "type[Entity] | SubqueryProxy", *, on: "AnyFilter") -> "QueryBuilder":
        table = other if isinstance(other, SubqueryProxy) else other.__table__
        return self._copy(joins=self.joins + (JoinClause(table, on, "inner"),))

    def left_join(self, other: "type[Entity] | SubqueryProxy", *, on: "AnyFilter") -> "QueryBuilder":
        table = other if isinstance(other, SubqueryProxy) else other.__table__
        return self._copy(joins=self.joins + (JoinClause(table, on, "left"),))

    def right_join(self, other: "type[Entity] | SubqueryProxy", *, on: "AnyFilter") -> "QueryBuilder":
        table = other if isinstance(other, SubqueryProxy) else other.__table__
        return self._copy(joins=self.joins + (JoinClause(table, on, "right"),))

    def cross_join(self, other: "type[Entity] | SubqueryProxy") -> "QueryBuilder":
        table = other if isinstance(other, SubqueryProxy) else other.__table__
        return self._copy(joins=self.joins + (JoinClause(table, None, "cross"),))

    def group_by(self, *proxies: "NormField[Any]") -> "QueryBuilder":
        return self._copy(group_bys=self.group_bys + proxies)

    def having(self, criterion: "AnyFilter") -> "QueryBuilder":
        return self._copy(havings=self.havings + (criterion,))

    def union(self, other: "QueryBuilder", *, all: bool = False) -> "UnionQuery":
        return UnionQuery(self, other, all=all)

    def as_view(self, alias: str) -> "SubqueryProxy":
        return SubqueryProxy(self, alias)

    def as_scalar(self) -> "ScalarSubquery":
        return ScalarSubquery(inner=self)

    def as_pypika(self, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        pika_cols = [col.to_column(params, dialect) for col in self.columns]
        q = pypika.Query.from_(self.source).select(*pika_cols)
        if self.is_distinct:
            q = q.distinct()
        for jc in self.joins:
            q = jc.apply_to(q, params, dialect, cte_names)
        for f in self.filters:
            q = q.where(f.to_pypika(params, dialect))
        for field, is_desc in self.orderings:
            order = pypika.enums.Order.desc if is_desc else pypika.enums.Order.asc
            q = q.orderby(field.pika_field, order=order)
        for gb in self.group_bys:
            q = q.groupby(gb.pika_field)
        for h in self.havings:
            q = q.having(h.to_pypika(params, dialect))
        if self.row_limit is not None:
            q = q.limit(self.row_limit)
        if self.row_offset is not None:
            q = q.offset(self.row_offset)
        return q

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        sql = self.as_pypika(params, dialect).get_sql(quote_char='"')
        return sql, tuple(params)


@dataclass(frozen=True)
class With:
    views: tuple[SubqueryProxy, ...]
    query: QueryBuilder
    recursive: bool = False

    def __init__(self, *views: SubqueryProxy, query: QueryBuilder, recursive: bool = False) -> None:
        object.__setattr__(self, "views", views)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "recursive", recursive)

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, tuple[Any, ...]]:
        params: list[Any] = []
        cte_names = frozenset(v.alias for v in self.views)
        cte_parts: list[str] = []
        for view in self.views:
            if isinstance(view.inner, UnionQuery):
                left_sql = view.inner.left.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
                right_sql = view.inner.right.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
                union_kw = "UNION ALL" if view.inner.all else "UNION"
                body_sql = f"{left_sql} {union_kw} {right_sql}"
            else:
                body_sql = view.inner.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
            cte_parts.append(f'"{view.alias}" AS ({body_sql})')
        main_sql = self.query.as_pypika(params, dialect, cte_names).get_sql(quote_char='"')
        prefix = "WITH RECURSIVE " if self.recursive else "WITH "
        return prefix + ", ".join(cte_parts) + " " + main_sql, tuple(params)
