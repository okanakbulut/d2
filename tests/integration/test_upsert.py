# pyright: basic
"""Integration tests for INSERT … ON CONFLICT (UPSERT) against live PostgreSQL."""

from typing import Any

import pytest

from norm import AsyncConnection, excluded
from .conftest import Accounts, AccountResult


@pytest.mark.asyncio(loop_scope="session")
async def test_upsert_do_update_with_excluded(pg_conn: Any) -> None:
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
    await conn.execute(Accounts.insert(name="Alice", email="alice@example.com", score=10))

    # Duplicate on email — should update name from the excluded row
    await conn.execute(
        Accounts.insert(name="Alicia", email="alice@example.com", score=10)
        .on_conflict(Accounts.email)
        .do_update(name=excluded(Accounts.name))
    )

    rows = await conn.fetch(Accounts.select_all(), list[AccountResult])
    assert len(rows) == 1
    assert rows[0].name == "Alicia"
    assert rows[0].email == "alice@example.com"


@pytest.mark.asyncio(loop_scope="session")
async def test_upsert_do_nothing(pg_conn: Any) -> None:
    await pg_conn.execute("DELETE FROM public.accounts")

    conn = AsyncConnection(pg_conn)
    await conn.execute(Accounts.insert(name="Bob", email="bob@example.com", score=5))

    # Duplicate — should be silently ignored
    await conn.execute(
        Accounts.insert(name="Bobby", email="bob@example.com", score=99)
        .on_conflict(Accounts.email)
        .do_nothing()
    )

    rows = await conn.fetch(Accounts.select_all(), list[AccountResult])
    assert len(rows) == 1
    assert rows[0].name == "Bob"
    assert rows[0].score == 5


@pytest.mark.asyncio(loop_scope="session")
async def test_upsert_bulk_do_update(pg_conn: Any) -> None:
    await pg_conn.execute("DELETE FROM public.accounts")

    conn = AsyncConnection(pg_conn)
    # Insert initial rows
    await conn.execute_many(Accounts.insert([
        {"name": "Alice", "email": "alice@example.com", "score": 10},
        {"name": "Bob",   "email": "bob@example.com",   "score": 20},
    ]))

    # Bulk upsert — both rows conflict; names should be updated
    await conn.execute_many(
        Accounts.insert([
            {"name": "Alicia", "email": "alice@example.com", "score": 10},
            {"name": "Bobby",  "email": "bob@example.com",   "score": 20},
        ])
        .on_conflict(Accounts.email)
        .do_update(name=excluded(Accounts.name))
    )

    rows = await conn.fetch(
        Accounts.select_all().order_by(Accounts.name),
        list[AccountResult],
    )
    assert len(rows) == 2
    assert rows[0].name == "Alicia"
    assert rows[1].name == "Bobby"
