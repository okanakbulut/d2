# pyright: basic
"""Integration tests for UPDATE and DELETE queries against a live PostgreSQL instance."""

from typing import Any

import pytest

from d2 import AsyncConnection
from .conftest import Accounts, AccountResult


@pytest.mark.asyncio(loop_scope="session")
async def test_update_and_delete(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.accounts (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            score INT NOT NULL DEFAULT 0
        )
    """)
    await pg_conn.execute("DELETE FROM public.accounts")

    conn = AsyncConnection(pg_conn)

    # Seed three rows
    await conn.execute(Accounts.insert(name="Alice", email="alice@example.com", score=10))
    await conn.execute(Accounts.insert(name="Bob", email="bob@example.com", score=20))
    await conn.execute(Accounts.insert(name="Charlie", email="charlie@example.com", score=30))

    # UPDATE: double score for rows with score >= 20
    await conn.execute(
        Accounts.update(score=Accounts.score * 2).where(Accounts.score >= 20)
    )

    # DELETE: remove rows with score > 50
    await conn.execute(
        Accounts.delete().where(Accounts.score > 50)
    )

    rows = await conn.fetch(
        Accounts.select_all().order_by(Accounts.name),
        list[AccountResult],
    )

    # Alice untouched (score=10), Bob updated (20*2=40), Charlie updated then deleted (30*2=60 > 50)
    assert len(rows) == 2
    assert rows[0].name == "Alice"
    assert rows[0].score == 10
    assert rows[1].name == "Bob"
    assert rows[1].score == 40
