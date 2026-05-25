"""Database-level expression primitives for norm model definitions.

Usage:
    from norm import db

    id:         PrimaryKey[int]          = field(default=db.serial())
    created_at: Field[datetime]          = field(default=db.now())
    org_id:     ForeignKey[Organization] = field(on_delete=db.CASCADE)
"""

from enum import StrEnum
from typing import Protocol


class DbExpr(Protocol):
    """Structural protocol for any database-level expression.

    Anything with a `.sql` property satisfies this — no inheritance required.
    """

    @property
    def sql(self) -> str: ...


class _DbFunc:
    __slots__ = ("_sql",)

    def __init__(self, sql: str) -> None:
        self._sql = sql

    @property
    def sql(self) -> str:
        return self._sql


class _SerialExpr(_DbFunc):
    """Sentinel for BIGSERIAL (sequence-backed integer PK). Handled specially by snapshot."""


def now() -> _DbFunc:
    """Database-side timestamp: NOW()."""
    return _DbFunc("NOW()")


def uuid() -> _DbFunc:
    """Database-side UUID: uuid_generate_v4()."""
    return _DbFunc("uuid_generate_v4()")


def serial() -> _SerialExpr:
    """Sequence-backed integer primary key (BIGSERIAL)."""
    return _SerialExpr("BIGSERIAL")


def value(v: int | str | bool) -> _DbFunc:
    """Literal database default value.

    Handles quoting: strings are single-quoted, booleans become TRUE/FALSE,
    integers are rendered as-is.
    """
    if isinstance(v, bool):
        return _DbFunc("TRUE" if v else "FALSE")
    if isinstance(v, int):
        return _DbFunc(str(v))
    escaped = v.replace("'", "''")
    return _DbFunc(f"'{escaped}'")


class ReferentialAction(StrEnum):
    CASCADE = "CASCADE"
    RESTRICT = "RESTRICT"
    SET_NULL = "SET NULL"
    SET_DEFAULT = "SET DEFAULT"
    NO_ACTION = "NO ACTION"


CASCADE = ReferentialAction.CASCADE
RESTRICT = ReferentialAction.RESTRICT
SET_NULL = ReferentialAction.SET_NULL
SET_DEFAULT = ReferentialAction.SET_DEFAULT
NO_ACTION = ReferentialAction.NO_ACTION
