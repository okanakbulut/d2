# pyright: basic
"""Integration tests for aggregation, GROUP BY, and HAVING against a live PostgreSQL instance."""

from typing import Any

import msgspec
import pytest

from d2 import AsyncConnection
from .conftest import Accounts

class AggRow(msgspec.Struct):
    name: str
    cnt: int
    avg_score: float


@pytest.mark.asyncio(loop_scope="session")
async def test_group_by_having_returns_expected_aggregates(pg_conn: Any) -> None:
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

    q = (
        Accounts.select(
            Accounts.name,
            Accounts.id.count().aliased("cnt"),
            Accounts.score.avg().aliased("avg_score"),
        )
        .group_by(Accounts.name)
        .having(Accounts.score.min() > 60)
        .order_by(Accounts.name)
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[AggRow])

    assert len(results) == 2
    assert results[0].name == "Alice"
    assert results[0].cnt == 1
    assert results[0].avg_score == 80.0
    assert results[1].name == "Charlie"
    assert results[1].cnt == 1
    assert results[1].avg_score == 95.0
