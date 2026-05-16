# pyright: basic
"""Integration tests for INSERT queries against a live PostgreSQL instance."""

from typing import Any

import msgspec
import pytest

from norm import AsyncConnection
from .conftest import Accounts, AccountResult

pytestmark = pytest.mark.integration


class InsertedAccount(msgspec.Struct):
    id: int
    name: str


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_single_row(pg_conn: Any) -> None:
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

    rows = await conn.fetch(Accounts.select_all(), list[AccountResult])
    assert len(rows) == 1
    assert rows[0].name == "Alice"
    assert rows[0].email == "alice@example.com"
    assert rows[0].score == 10


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_bulk(pg_conn: Any) -> None:
    await pg_conn.execute("DELETE FROM public.accounts")

    conn = AsyncConnection(pg_conn)
    await conn.execute_many(Accounts.insert([
        {"name": "Alice", "email": "alice@example.com", "score": 10},
        {"name": "Bob",   "email": "bob@example.com",   "score": 20},
    ]))

    rows = await conn.fetch(
        Accounts.select_all().order_by(Accounts.name),
        list[AccountResult],
    )
    assert len(rows) == 2
    assert rows[0].name == "Alice"
    assert rows[1].name == "Bob"


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_returning_server_generated_id(pg_conn: Any) -> None:
    await pg_conn.execute("DELETE FROM public.accounts")

    conn = AsyncConnection(pg_conn)
    q = Accounts.insert(name="Charlie", email="charlie@example.com", score=5).returning(
        Accounts.id, Accounts.name
    )
    result = await conn.fetch(q, InsertedAccount)

    assert result is not None
    assert result.id > 0
    assert result.name == "Charlie"
