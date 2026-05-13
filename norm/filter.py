
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pypika.terms

if TYPE_CHECKING:
    from .schema import Field


@dataclass(frozen=True)
class Filter:
    field: Field[Any]
    value: Any

    def to_pypika(self, params: list[Any], dialect: Any) -> pypika.terms.Criterion:
        params.append(self.value)
        return self.field.pika_field == pypika.terms.Parameter(dialect.placeholder(len(params)))
