"""Shared fixtures and models for integration tests."""

import os, pathlib, typing

import pytest, msgspec, asyncpg


from norm import db
from norm import TableMeta, Table, PrimaryKey, Unique, Field, field

PG_DSN = os.getenv("NORM_TEST_DSN", "postgresql://norm:norm@localhost:5432/norm_test")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test under tests/integration/ requires a running PostgreSQL."""
    here = pathlib.Path(__file__).parent
    for item in items:
        if item.path.is_relative_to(here):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
async def pg_conn() -> typing.AsyncGenerator[asyncpg.Connection, None]:
    conn = typing.cast(asyncpg.Connection, await asyncpg.connect(PG_DSN)) # type: ignore[reportUnknownMemberType]
    yield conn
    await conn.close() # type: ignore[reportUnknownMemberType]


class Accounts(Table):
    __meta__ = TableMeta(table="accounts", schema="public")
    id:    PrimaryKey[int] = field(default=db.serial())
    name:  Field[str]
    email: Unique[str]
    score: Field[int]


class AccountResult(msgspec.Struct):
    id: int
    name: str
    email: str
    score: int


class AccountSummary(msgspec.Struct):
    display_name: str
    score: int


class TxnAccounts(Table):
    __meta__ = TableMeta(table="txn_accounts", schema="public")
    id:    PrimaryKey[int] = field(default=db.serial())
    name:  Field[str]
    email: Unique[str]
