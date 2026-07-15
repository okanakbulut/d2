
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any

import pypika.terms

if TYPE_CHECKING:
    from .schema import Field


@dataclass(frozen=True)
class Filter:
    field: "Field[Any]"
    value: Any
    op: str = dc_field(default="eq")

    def __and__(self, other: "Filter | CompoundFilter") -> "CompoundFilter":
        return CompoundFilter(left=self, right=other, op="and")

    def __or__(self, other: "Filter | CompoundFilter") -> "CompoundFilter":
        return CompoundFilter(left=self, right=other, op="or")

    def to_pypika(self, params: list[Any], dialect: Any) -> pypika.terms.Criterion:
        from .query import ScalarSubquery

        col = self.field.pika_field

        if isinstance(self.value, ScalarSubquery):
            inner_pika = self.value.inner.as_pypika(params, dialect)
            ops = {
                "eq": col == inner_pika,
                "ne": col != inner_pika,
                "lt": col < inner_pika,
                "lte": col <= inner_pika,
                "gt": col > inner_pika,
                "gte": col >= inner_pika,
            }
            if self.op not in ops:
                raise ValueError(f"op {self.op!r} not supported with scalar subquery")
            return ops[self.op]

        if self.op == "col_eq":
            return col == self.value.pika_field

        if self.op == "eq":
            params.append(self.value)
            return col == pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "ne":
            params.append(self.value)
            return col != pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "lt":
            params.append(self.value)
            return col < pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "lte":
            params.append(self.value)
            return col <= pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "gt":
            params.append(self.value)
            return col > pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "gte":
            params.append(self.value)
            return col >= pypika.terms.Parameter(dialect.placeholder(len(params)))

        if self.op == "like":
            params.append(self.value)
            return col.like(pypika.terms.Parameter(dialect.placeholder(len(params))))

        if self.op == "ilike":
            params.append(self.value)
            return col.ilike(pypika.terms.Parameter(dialect.placeholder(len(params))))

        if self.op == "null":
            return col.isnull()

        if self.op == "notnull":
            return col.isnotnull()

        if self.op == "between":
            lo, hi = self.value
            params.append(lo)
            lo_param = pypika.terms.Parameter(dialect.placeholder(len(params)))
            params.append(hi)
            hi_param = pypika.terms.Parameter(dialect.placeholder(len(params)))
            return col.between(lo_param, hi_param)

        if self.op in ("in", "notin"):
            placeholders: list[pypika.terms.Term] = []
            for v in self.value:
                params.append(v)
                placeholders.append(pypika.terms.Parameter(dialect.placeholder(len(params))))
            if self.op == "in":
                return col.isin(placeholders)
            return col.notin(placeholders)

        raise ValueError(f"unknown filter op: {self.op!r}")


@dataclass(frozen=True)
class CompoundFilter:
    left: "Filter | CompoundFilter"
    right: "Filter | CompoundFilter"
    op: str  # "and" | "or"

    def __and__(self, other: "Filter | CompoundFilter") -> "CompoundFilter":
        return CompoundFilter(left=self, right=other, op="and")

    def __or__(self, other: "Filter | CompoundFilter") -> "CompoundFilter":
        return CompoundFilter(left=self, right=other, op="or")

    def to_pypika(self, params: list[Any], dialect: Any) -> pypika.terms.Criterion:
        l = self.left.to_pypika(params, dialect)
        r = self.right.to_pypika(params, dialect)
        if self.op == "and":
            return l & r
        return l | r


AnyFilter = Filter | CompoundFilter
