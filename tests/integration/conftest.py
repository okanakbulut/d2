"""Shared fixtures and models for integration tests."""

import os
from typing import Any, AsyncGenerator

import pytest
import asyncpg  # type: ignore[import-untyped]
import msgspec

from norm import TableMeta, Table, PrimaryKey, Unique, Field, field

PG_DSN = os.getenv("NORM_TEST_DSN", "postgresql://norm:norm@localhost:5432/norm_test")


@pytest.fixture(scope="session")
async def pg_conn() -> AsyncGenerator[Any, None]:
    conn: Any = await asyncpg.connect(PG_DSN)
    yield conn
    await conn.close()


class Accounts(Table):
    __meta__ = TableMeta(table="accounts", schema="public")
    id:    PrimaryKey[int] = field(db_default=True)
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
    id:    PrimaryKey[int] = field(db_default=True)
    name:  Field[str]
    email: Unique[str]
