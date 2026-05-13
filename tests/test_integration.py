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


class AccountResult(msgspec.Struct):
    id: int
    name: str
    email: str


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="session")
async def test_select_round_trip(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.accounts (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
    """)
    await pg_conn.execute("DELETE FROM public.accounts")

    await pg_conn.execute(
        "INSERT INTO public.accounts (name, email) VALUES ($1, $2)",
        "Alice",
        "alice@example.com",
    )

    q = Accounts.select(Accounts.id, Accounts.name, Accounts.email).where(
        Accounts.email == "alice@example.com"
    )

    conn = AsyncConnection(pg_conn)
    results: list[AccountResult] = await conn.fetch(q, AccountResult)

    assert len(results) == 1
    assert results[0].name == "Alice"
    assert results[0].email == "alice@example.com"
    assert isinstance(results[0].id, int)

    # cleanup
    await pg_conn.execute("DROP TABLE IF EXISTS public.accounts")
