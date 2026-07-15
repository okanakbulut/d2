# pyright: basic
"""Integration tests for transaction commit and rollback against a live PostgreSQL instance."""

from typing import Any

import pytest

from d2 import AsyncConnection
from .conftest import TxnAccounts


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
        await conn.execute(TxnAccounts.insert(name="Bob",   email="bob@txn.com"))

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
