# pyright: basic
"""Integration tests — require a running PostgreSQL instance.

Run with:
    docker compose up -d
    uv run pytest tests/test_integration.py -m integration -v
"""

import os
from typing import Any, AsyncGenerator

import pytest
import asyncpg  # type: ignore[import-untyped]

import msgspec

from norm import (
    TableMeta, Table, PrimaryKey, Unique, Field, field,
    AsyncConnection,
)


pytestmark = pytest.mark.integration

PG_DSN = os.getenv("NORM_TEST_DSN", "postgresql://norm:norm@localhost:5432/norm_test")



@pytest.fixture(scope="session")
async def pg_conn() -> AsyncGenerator[Any, None]:
    conn: Any = await asyncpg.connect(PG_DSN)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Model + result struct for the integration test
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="session")
async def test_select_round_trip(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.accounts (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            score INT NOT NULL DEFAULT 0
        )
    """)
    await pg_conn.execute("DELETE FROM public.accounts")

    await pg_conn.execute(
        "INSERT INTO public.accounts (name, email, score) VALUES ($1, $2, $3)",
        "Alice", "alice@example.com", 80,
    )
    await pg_conn.execute(
        "INSERT INTO public.accounts (name, email, score) VALUES ($1, $2, $3)",
        "Bob", "bob@example.com", 50,
    )
    await pg_conn.execute(
        "INSERT INTO public.accounts (name, email, score) VALUES ($1, $2, $3)",
        "Charlie", "charlie@example.com", 95,
    )

    q = Accounts.select(Accounts.id, Accounts.name, Accounts.email, Accounts.score).where(
        Accounts.email == "alice@example.com"
    )

    conn = AsyncConnection(pg_conn)
    results: list[AccountResult] = await conn.fetch(q, list[AccountResult])

    assert len(results) == 1
    assert results[0].name == "Alice"
    assert results[0].email == "alice@example.com"
    assert isinstance(results[0].id, int)


@pytest.mark.asyncio(loop_scope="session")
async def test_predicates_ordering_aliasing(pg_conn: Any) -> None:
    """Three predicate types + order_by + limit + offset + aliased column."""
    q = (
        Accounts
        .select(Accounts.name.as_("display_name"), Accounts.score)
        .where(Accounts.score.between(50, 90))   # predicate 1: BETWEEN
        .where(Accounts.email.isnotnull())         # predicate 2: IS NOT NULL
        .where(Accounts.name.ilike("a%"))          # predicate 3: ILIKE
        .order_by(Accounts.score, desc=True)
        .limit(10)
        .offset(0)
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[AccountSummary])

    assert len(results) == 1
    assert results[0].display_name == "Alice"
    assert results[0].score == 80

    # cleanup (done here so it runs after both tests)
    await pg_conn.execute("DROP TABLE IF EXISTS public.accounts")


@pytest.mark.asyncio(loop_scope="session")
async def test_transaction_commit(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.txn_accounts (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
    """)
    await pg_conn.execute("DELETE FROM public.txn_accounts")

    conn = AsyncConnection(pg_conn)
    async with conn.transaction():
        await conn.execute(TxnAccounts.insert(name="Alice", email="alice@txn.com"))
        await conn.execute(TxnAccounts.insert(name="Bob", email="bob@txn.com"))

    rows = await pg_conn.fetch("SELECT name FROM public.txn_accounts ORDER BY name")
    assert [r["name"] for r in rows] == ["Alice", "Bob"]

    await pg_conn.execute("DROP TABLE IF EXISTS public.txn_accounts")


@pytest.mark.asyncio(loop_scope="session")
async def test_transaction_rollback_on_exception(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.txn_accounts (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
    """)
    await pg_conn.execute("DELETE FROM public.txn_accounts")

    conn = AsyncConnection(pg_conn)
    try:
        async with conn.transaction():
            await conn.execute(TxnAccounts.insert(name="Charlie", email="charlie@txn.com"))
            raise RuntimeError("abort")
    except RuntimeError:
        pass

    rows = await pg_conn.fetch("SELECT name FROM public.txn_accounts")
    assert rows == []

    await pg_conn.execute("DROP TABLE IF EXISTS public.txn_accounts")
