# pyright: basic
"""Integration tests for subquery features: aliased subqueries and as_scalar()."""

from typing import Any

import msgspec
import pytest

from norm import AsyncConnection, TableMeta, Table, PrimaryKey, Field, field

pytestmark = pytest.mark.integration


class SubqOrders(Table):
    __meta__ = TableMeta(table="subq_orders", schema="public")
    id:      PrimaryKey[int] = field(db_default=True)
    user_id: Field[int]
    amount:  Field[int]


class SubqUsers(Table):
    __meta__ = TableMeta(table="subq_users", schema="public")
    id:   PrimaryKey[int] = field(db_default=True)
    name: Field[str]


class UserRevenue(msgspec.Struct):
    name: str
    total: int


@pytest.mark.asyncio(loop_scope="session")
async def test_join_against_grouped_subquery(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.subq_users (
            id   SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.subq_orders (
            id      SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            amount  INT NOT NULL
        )
    """)
    await pg_conn.execute("DELETE FROM public.subq_orders")
    await pg_conn.execute("DELETE FROM public.subq_users")

    alice_id: int = await pg_conn.fetchval(
        "INSERT INTO public.subq_users (name) VALUES ($1) RETURNING id", "Alice"
    )
    bob_id: int = await pg_conn.fetchval(
        "INSERT INTO public.subq_users (name) VALUES ($1) RETURNING id", "Bob"
    )
    for amount in [500, 700]:
        await pg_conn.execute(
            "INSERT INTO public.subq_orders (user_id, amount) VALUES ($1, $2)", alice_id, amount
        )
    await pg_conn.execute(
        "INSERT INTO public.subq_orders (user_id, amount) VALUES ($1, $2)", bob_id, 200
    )

    revenue_by_user = (
        SubqOrders
        .select(SubqOrders.user_id, SubqOrders.amount.sum().aliased("total"))
        .group_by(SubqOrders.user_id)
        .aliased("rev")
    )
    q = (
        SubqUsers
        .select(SubqUsers.name, revenue_by_user.total)  # type: ignore[attr-defined]
        .join(revenue_by_user, on=SubqUsers.id == revenue_by_user.user_id)  # type: ignore[attr-defined]
        .where(revenue_by_user.total > 500)  # type: ignore[attr-defined]
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserRevenue])

    assert len(results) == 1
    assert results[0].name == "Alice"
    assert results[0].total == 1200


@pytest.mark.asyncio(loop_scope="session")
async def test_scalar_subquery_in_where(pg_conn: Any) -> None:
    avg_score_qb = SubqOrders.select(SubqOrders.amount.avg())
    q = SubqOrders.select(SubqOrders.user_id, SubqOrders.amount).where(
        SubqOrders.amount > avg_score_qb.as_scalar()
    )

    conn = AsyncConnection(pg_conn)

    class OrderRow(msgspec.Struct):
        user_id: int
        amount: int

    class AmountRow(msgspec.Struct):
        amount: int

    results = await conn.fetch(q, list[OrderRow])
    all_rows = await conn.fetch(SubqOrders.select(SubqOrders.amount), list[AmountRow])
    overall_avg = sum(r.amount for r in all_rows) / len(all_rows)
    assert all(r.amount > overall_avg for r in results)
