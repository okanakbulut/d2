
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any, cast

import pypika
import pypika.enums
import pypika.terms

from .dialect import Dialect, PostgresDialect

if TYPE_CHECKING:
    from .filter import Filter, AnyFilter
    from .schema import Field as NormField, Selectable


@dataclass(frozen=True)
class ConflictBuilder:
    """Intermediate/terminal builder produced by InsertQuery.on_conflict()."""

    insert: Any  # InsertQuery
    targets: tuple[Any, ...]  # tuple[NormField, ...]
    action: str = ""  # "nothing" | "update"
    assignments: tuple[tuple[str, Any], ...] = dc_field(default_factory=tuple)
    returning_fields: tuple[Any, ...] = dc_field(default_factory=tuple)  # tuple[NormField, ...]

    def do_nothing(self) -> "ConflictBuilder":
        return ConflictBuilder(insert=self.insert, targets=self.targets, action="nothing")

    def do_update(self, **kwargs: Any) -> "ConflictBuilder":
        assignments = tuple((k, v) for k, v in kwargs.items())
        return ConflictBuilder(
            insert=self.insert, targets=self.targets,
            action="update", assignments=assignments,
        )

    update = do_update

    def returning(self, *fields: Any) -> "ConflictBuilder":
        return ConflictBuilder(
            insert=self.insert, targets=self.targets,
            action=self.action, assignments=self.assignments,
            returning_fields=fields,
        )

    def build(self, dialect: Dialect = PostgresDialect()) -> tuple[str, Any]:
        base_sql, base_params = self.insert.build(dialect)

        target_cols = ", ".join(f'"{p.column_name}"' for p in self.targets)

        if self.action == "nothing":
            sql = f"{base_sql} ON CONFLICT ({target_cols}) DO NOTHING"
        else:
            # "update" — build SET clause
            n_insert_cols = len(self.insert.rows[0])
            # Seed offset_params with n_insert_cols dummy entries so that
            # to_column() appends literals at the correct positional indices ($N+1…).
            offset_params: list[Any] = [None] * n_insert_cols

            set_parts: list[str] = []
            for col_name, value in self.assignments:
                from .schema import Field as NormField
                if isinstance(value, NormField):
                    term = value.to_column(offset_params, dialect)
                    term_sql = term.get_sql(quote_char='"')
                else:
                    offset_params.append(value)
                    term_sql = dialect.placeholder(len(offset_params))
                set_parts.append(f'"{col_name}"={term_sql}')

            conflict_values = offset_params[n_insert_cols:]
            set_clause = ", ".join(set_parts)
            sql = f"{base_sql} ON CONFLICT ({target_cols}) DO UPDATE SET {set_clause}"

            if self.insert.is_many:
                base_params = [row + tuple(conflict_values) for row in base_params]
            else:
                base_params = base_params + tuple(conflict_values)

        if self.returning_fields:
            ret_cols = ",".join(f.pika_field.get_sql(quote_char='"') for f in self.returning_fields)
            sql = f"{sql} RETURNING {ret_cols}"

        return sql, base_params


@dataclass(frozen=True)
class ScalarSubquery:
    inner: Any  # Entity clone type (Selectable subclass)


@dataclass(frozen=True)
class JoinClause:
    table: pypika.Table | type[Selectable]
    criterion: AnyFilter | None
    kind: str  # "inner" | "left" | "right" | "cross"

    def apply_to(self, q: Any, params: list[Any], dialect: Dialect, cte_names: frozenset[str] = frozenset()) -> Any:
        if isinstance(self.table, type):
            # Entity clone used as join target (has __alias__ and __inner__)
            alias: str = cast(str, self.table.__alias__)
            inner: Any = self.table.__inner__
            if inner is not None and alias not in cte_names:
                # Render as inline subquery
                from pypika.queries import JoinOn, Join as PikaJoin
                union_left: Any = getattr(inner, "__union_left__", None)
                if union_left is not None:
                    left_pika: Any = getattr(union_left, "as_pypika")(params, dialect)
                    union_right: Any = getattr(inner, "__union_right__")
                    right_pika: Any = getattr(union_right, "as_pypika")(params, dialect)
                    if getattr(inner, "__union_all__", False):
                        inner_pika: Any = getattr(left_pika, "union_all")(right_pika)
                    else:
                        inner_pika = getattr(left_pika, "union")(right_pika)
                else:
                    inner_pika = getattr(inner, "as_pypika")(params, dialect)
                join_target: Any = getattr(inner_pika, "as_")(alias)
                join_type_map = {
                    "inner": pypika.enums.JoinType.inner,
                    "left": pypika.enums.JoinType.left,
                    "right": pypika.enums.JoinType.right,
                }
                _joins: list[Any] = getattr(q, "_joins")
                if self.kind == "cross":
                    _joins.append(PikaJoin(join_target, pypika.enums.JoinType.cross))
                else:
                    assert self.criterion is not None
                    criterion_pika = self.criterion.to_pypika(params, dialect)
                    _joins.append(JoinOn(join_target, join_type_map[self.kind], cast(Any, criterion_pika), None))
                return q
            # CTE reference: alias is in cte_names, use it as a plain table name
            pika_table = pypika.Table(alias)
        else:
            # Regular pypika.Table (possibly with alias for real table aliases)
            pika_table = self.table

        if self.kind == "cross":
            return q.join(pika_table, pypika.enums.JoinType.cross).cross()
        assert self.criterion is not None
        if self.kind == "inner":
            return q.join(pika_table).on(self.criterion.to_pypika(params, dialect))
        elif self.kind == "left":
            return q.left_join(pika_table).on(self.criterion.to_pypika(params, dialect))
        elif self.kind == "right":
            return q.right_join(pika_table).on(self.criterion.to_pypika(params, dialect))
        return q


@dataclass(frozen=True)
class InsertQuery:
    source: pypika.Table
    rows: tuple[dict[str, Any], ...]
    is_many: bool = False
    returning_fields: tuple[NormField[Any], ...] = dc_field(default_factory=tuple)

    def returning(self, *fields: NormField[Any]) -> InsertQuery:
        return InsertQuery(
            source=self.source, rows=self.rows,
            is_many=self.is_many, returning_fields=fields,
        )

    def on_conflict(self, *proxies: NormField[Any]) -> ConflictBuilder:
        return ConflictBuilder(insert=self, targets=proxies)

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
    assignments: tuple[tuple[str, Any], ...]
    filters: tuple[Filter, ...] = dc_field(default_factory=tuple)

    def where(self, filter: Filter) -> UpdateQuery:
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
    filters: tuple[Filter, ...] = dc_field(default_factory=tuple)

    def where(self, filter: Filter) -> DeleteQuery:
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
