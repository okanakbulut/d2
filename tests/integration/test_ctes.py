"""Integration tests for CTEs against a live PostgreSQL instance."""

from typing import Any

import msgspec
import pytest

from d2 import db
from d2 import AsyncConnection, TableMeta, Table, PrimaryKey, Field, field, With


class Employees(Table):
    __meta__ = TableMeta(table="cte_employees", schema="public")
    id:         PrimaryKey[int] = field(default=db.serial())
    name:       Field[str]
    manager_id: Field[int]


class EmployeeRow(msgspec.Struct):
    id: int
    name: str
    manager_id: int | None


@pytest.fixture(scope="module", autouse=True)
async def employee_fixture(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.cte_employees (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            manager_id INT REFERENCES public.cte_employees(id)
        )
    """)
    await pg_conn.execute("DELETE FROM public.cte_employees")
    # Tree:  Alice(1) ← root
    #          Bob(2), Carol(3) report to Alice
    #          Dave(4) reports to Bob
    await pg_conn.execute(
        "INSERT INTO public.cte_employees (id, name, manager_id) VALUES ($1,$2,$3),($4,$5,$6),($7,$8,$9),($10,$11,$12)",
        1, "Alice", None,
        2, "Bob",   1,
        3, "Carol", 1,
        4, "Dave",  2,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_named_cte_filters_root_employees(pg_conn: Any) -> None:
    roots = (
        Employees.select(Employees.id, Employees.name)
        .where(Employees.manager_id.isnull())
        .aliased("roots")
    )
    q = With(
        roots,
        query=(
            Employees.select(Employees.id, Employees.name, Employees.manager_id)
            .join(roots, on=Employees.id == roots.id)
        ),
    )

    conn = AsyncConnection(pg_conn)
    rows = await conn.fetch(q, list[EmployeeRow])
    assert {r.name for r in rows} == {"Alice"}


@pytest.mark.asyncio(loop_scope="session")
async def test_recursive_cte_subtree_under_mid_node(pg_conn: Any) -> None:
    anchor = (
        Employees.select(Employees.id, Employees.name, Employees.manager_id)
        .where(Employees.id == 2)
    )
    bob_tree_ref = anchor.aliased("bob_tree")
    step = (
        Employees.select(Employees.id, Employees.name, Employees.manager_id)
        .join(bob_tree_ref, on=Employees.manager_id == bob_tree_ref.id)
    )
    bob_tree = anchor.union(step, all=True).aliased("bob_tree")
    q = With(
        bob_tree,
        query=(
            Employees.select(Employees.id, Employees.name, Employees.manager_id)
            .join(bob_tree, on=Employees.id == bob_tree.id)
        ),
        recursive=True,
    )

    conn = AsyncConnection(pg_conn)
    rows = await conn.fetch(q, list[EmployeeRow])
    assert {r.name for r in rows} == {"Bob", "Dave"}


@pytest.mark.asyncio(loop_scope="session")
async def test_recursive_cte_returns_full_subtree(pg_conn: Any) -> None:
    anchor = (
        Employees.select(Employees.id, Employees.name, Employees.manager_id)
        .where(Employees.id == 1)
    )
    org_cte_ref = anchor.aliased("org_cte")
    step = (
        Employees.select(Employees.id, Employees.name, Employees.manager_id)
        .join(org_cte_ref, on=Employees.manager_id == org_cte_ref.id)
    )
    org_cte = anchor.union(step, all=True).aliased("org_cte")
    q = With(
        org_cte,
        query=(
            Employees.select(Employees.id, Employees.name, Employees.manager_id)
            .join(org_cte, on=Employees.id == org_cte.id)
        ),
        recursive=True,
    )

    conn = AsyncConnection(pg_conn)
    rows = await conn.fetch(q, list[EmployeeRow])
    assert {r.name for r in rows} == {"Alice", "Bob", "Carol", "Dave"}
