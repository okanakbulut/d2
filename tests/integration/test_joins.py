# pyright: basic
"""Integration test: self-join over employee/manager fixture."""

from typing import Any

import msgspec
import pytest

from norm import db
from norm import AsyncConnection, TableMeta, Table, PrimaryKey, Field, field


class Employees(Table):
    __meta__ = TableMeta(table="join_employees", schema="public")
    id:         PrimaryKey[int] = field(default=db.serial())
    name:       Field[str]
    manager_id: Field[int]


class ManagerReport(msgspec.Struct):
    manager_name: str
    report_name: str


@pytest.mark.asyncio(loop_scope="session")
async def test_self_join_returns_manager_report_pairs(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.join_employees (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            manager_id INT
        )
    """)
    await pg_conn.execute("DELETE FROM public.join_employees")

    alice_id = await pg_conn.fetchval(
        "INSERT INTO public.join_employees (name, manager_id) VALUES ($1, $2) RETURNING id",
        "Alice", None,
    )
    await pg_conn.execute(
        "INSERT INTO public.join_employees (name, manager_id) VALUES ($1, $2)",
        "Bob", alice_id,
    )
    await pg_conn.execute(
        "INSERT INTO public.join_employees (name, manager_id) VALUES ($1, $2)",
        "Carol", alice_id,
    )

    Mgr = Employees.aliased("mgr")
    Rep = Employees.aliased("rep")

    q = (
        Mgr.select(Mgr.name.aliased("manager_name"), Rep.name.aliased("report_name"))
        .join(Rep, on=Mgr.id == Rep.manager_id)
        .order_by(Rep.name)
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[ManagerReport])

    assert len(results) == 2
    assert results[0].manager_name == "Alice"
    assert results[0].report_name == "Bob"
    assert results[1].manager_name == "Alice"
    assert results[1].report_name == "Carol"
