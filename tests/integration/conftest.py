"""Shared fixtures and models for integration tests."""

import json as json_module
import os, typing

import pytest, msgspec, asyncpg


from norm import TableMeta, Table, PrimaryKey, Unique, Field, field

PG_DSN = os.getenv("NORM_TEST_DSN", "postgresql://norm:norm@localhost:5432/norm_test")


@pytest.fixture(scope="session")
async def pg_conn() -> typing.AsyncGenerator[asyncpg.Connection, None]:
    conn = typing.cast(asyncpg.Connection, await asyncpg.connect(PG_DSN)) # type: ignore[reportUnknownMemberType]
    # await conn.set_type_codec("json", encoder=json_module.dumps, decoder=json_module.loads, schema="pg_catalog") # type: ignore[reportUnknownMemberType]
    yield conn
    await conn.close() # type: ignore[reportUnknownMemberType]


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
