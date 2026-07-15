
from typing import Protocol, runtime_checkable


@runtime_checkable
class Dialect(Protocol):
    def placeholder(self, n: int) -> str: ...


class PostgresDialect:
    def placeholder(self, n: int) -> str:
        return f"${n}"
