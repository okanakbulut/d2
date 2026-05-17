# pyright: basic
"""Integration tests for set operations against a live PostgreSQL instance."""

from typing import Any

import pytest

from norm import AsyncConnection
from .conftest import Accounts, AccountResult


@pytest.fixture(autouse=True, scope="module")
async def accounts_table(pg_conn: Any) -> None:
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



@pytest.mark.asyncio(loop_scope="session")
async def test_union_returns_combined_rows(pg_conn: Any) -> None:
    high = Accounts.select(Accounts.id, Accounts.name, Accounts.email, Accounts.score).where(Accounts.score >= 80)
    low  = Accounts.select(Accounts.id, Accounts.name, Accounts.email, Accounts.score).where(Accounts.score < 60)

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(high.union(low), list[AccountResult])

    names = {r.name for r in results}
    assert names == {"Alice", "Charlie", "Bob"}


@pytest.mark.asyncio(loop_scope="session")
async def test_union_with_order_by_and_limit(pg_conn: Any) -> None:
    high = Accounts.select(Accounts.id, Accounts.name, Accounts.email, Accounts.score).where(Accounts.score >= 50)
    low  = Accounts.select(Accounts.id, Accounts.name, Accounts.email, Accounts.score).where(Accounts.score < 60)

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(
        high.union(low).order_by(Accounts.score).limit(2),
        list[AccountResult],
    )

    assert len(results) == 2
    assert results[0].score <= results[1].score
