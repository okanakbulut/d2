# pyright: basic
"""Integration tests for SELECT queries against a live PostgreSQL instance."""

from typing import Any

import pytest

from norm import AsyncConnection
from .conftest import Accounts, AccountResult, AccountSummary


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
    results = await conn.fetch(q, list[AccountResult])

    assert len(results) == 1
    assert results[0].name == "Alice"
    assert results[0].email == "alice@example.com"
    assert isinstance(results[0].id, int)


@pytest.mark.asyncio(loop_scope="session")
async def test_predicates_ordering_aliasing(pg_conn: Any) -> None:
    """Exercises BETWEEN, IS NOT NULL, ILIKE, ORDER BY, LIMIT, OFFSET, and column alias."""
    q = (
        Accounts
        .select(Accounts.name.aliased("display_name"), Accounts.score)
        .where(Accounts.score.between(50, 90))
        .where(Accounts.email.isnotnull())
        .where(Accounts.name.ilike("a%"))
        .order_by(Accounts.score, desc=True)
        .limit(10)
        .offset(0)
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[AccountSummary])

    assert len(results) == 1
    assert results[0].display_name == "Alice"
    assert results[0].score == 80

    await pg_conn.execute("DROP TABLE IF EXISTS public.accounts")
