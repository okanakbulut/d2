
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any

import pypika
import pypika.enums
import pypika.terms

from .dialect import Dialect, PostgresDialect

if TYPE_CHECKING:
    from .filter import Filter, AnyFilter
    from .schema import Field as NormField


@dataclass(frozen=True)
class ScalarSubquery:
    inner: Any  # Entity clone type (Selectable subclass)


@dataclass(frozen=True)
class JoinClause:
    table: Any  # pypika.Table for entity joins, Entity clone type for subquery/CTE joins
    criterion: "AnyFilter | None"
    kind: str  # "inner" | "left" | "right" | "cross"

    def apply_to(self, q: Any, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        if isinstance(self.table, type):
            # Entity clone used as join target (has __alias__ and __inner__)
            alias: str = self.table.__alias__
            inner = self.table.__inner__
            if inner is not None and alias not in cte_names:
                # Render as inline subquery
                from pypika.queries import JoinOn, Join as PikaJoin
                union_left = getattr(inner, "__union_left__", None)
                if union_left is not None:
                    left_pika = union_left.as_pypika(params, dialect)
                    right_pika = inner.__union_right__.as_pypika(params, dialect)
                    if inner.__union_all__:
                        inner_pika = left_pika.union_all(right_pika)
                    else:
                        inner_pika = left_pika.union(right_pika)
                else:
                    inner_pika = inner.as_pypika(params, dialect)
                join_target = inner_pika.as_(alias)
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
            # CTE reference: alias is in cte_names, use it as a plain table name
            pika_table = pypika.Table(alias)
        else:
            # Regular pypika.Table (possibly with alias for real table aliases)
            pika_table = self.table

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
        q = pypika.Query.update(self.source)  # type: ignore[no-untyped-call]
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


def With(*ctes: Any, query: Any, recursive: bool = False) -> Any:
    """Create a CTE query by cloning query and attaching named CTE views."""
    q = query.clone()
    q.__ctes__ = ctes
    q.__recursive__ = recursive
    return q
