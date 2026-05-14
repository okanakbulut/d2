
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

    def to_pypika(self, params: list[Any], dialect: Any) -> pypika.terms.Criterion:
        col = self.field.pika_field

        if self.op == "col_eq":
            return col == self.value.pika_field  # type: ignore[union-attr]

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
