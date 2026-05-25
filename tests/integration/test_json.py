"""Integration tests for .json() query modifier."""

import json
from typing import Any

import pytest

from norm import db
from norm import AsyncConnection, Table, PrimaryKey, Unique, Field, TableMeta, field


class JUsers(Table):
    __meta__ = TableMeta(table="j_users", schema="public")
    id:    PrimaryKey[int] = field(default=db.serial())
    name:  Field[str]
    email: Unique[str]


@pytest.fixture(autouse=True)
async def setup_tables(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.j_users (
            id    SERIAL PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
    """)
    await pg_conn.execute("DELETE FROM public.j_users")
    await pg_conn.execute(
        "INSERT INTO public.j_users (name, email) VALUES ($1, $2)", "Alice", "alice@example.com"
    )
    await pg_conn.execute(
        "INSERT INTO public.j_users (name, email) VALUES ($1, $2)", "Bob", "bob@example.com"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_json_single_row_returns_str(pg_conn: Any) -> None:
    """Without alias, .json() wraps in row_to_json — fetchval returns a raw JSON string."""
    conn = AsyncConnection(pg_conn)
    result = await conn.fetchval(
        JUsers.select(JUsers.id, JUsers.name, JUsers.email)
        .where(JUsers.name == "Alice")
        .json()
    )
    assert isinstance(result, str)
    data = json.loads(result)
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert isinstance(data["id"], int)

@pytest.mark.asyncio(loop_scope="session")
async def test_json_single_row_returns_object(pg_conn: Any) -> None:
    """Without alias, .json() wraps in row_to_json — fetchval returns a raw JSON string."""
    conn = AsyncConnection(pg_conn)
    result = await conn.fetch(
        JUsers.select(JUsers.id, JUsers.name, JUsers.email)
        .where(JUsers.name == "Alice")
        .json(),
        dict[str, Any],
    )
    assert isinstance(result, dict)
    assert result["name"] == "Alice"
    assert result["email"] == "alice@example.com"
    assert isinstance(result["id"], int)

@pytest.mark.asyncio(loop_scope="session")
async def test_json_aliased_returns_str_with_list(pg_conn: Any) -> None:
    """.aliased("users").json() wraps in json_build_object — result is a raw JSON string."""
    conn = AsyncConnection(pg_conn)
    result = await conn.fetchval(
        JUsers.select(JUsers.name, JUsers.email)
        .order_by(JUsers.name)
        .aliased("users")
        .json()
    )
    assert isinstance(result, str)
    data = json.loads(result)
    assert "users" in data
    rows = data["users"]
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"



@pytest.mark.asyncio(loop_scope="session")
async def test_json_aliased_returns_object_with_list(pg_conn: Any) -> None:
    """.aliased("users").json() wraps in json_build_object — result is a raw JSON string."""
    conn = AsyncConnection(pg_conn)
    result = await conn.fetch(
        JUsers.select(JUsers.name, JUsers.email)
        .order_by(JUsers.name)
        .aliased("users")
        .json(),
        dict[str, Any],
    )
    assert isinstance(result, dict)
    assert "users" in result
    rows = result["users"]
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"

@pytest.mark.asyncio(loop_scope="session")
async def test_json_aliased_empty_table_returns_empty_list(pg_conn: Any) -> None:
    """COALESCE ensures an empty result gives [] rather than NULL."""
    await pg_conn.execute("DELETE FROM public.j_users")
    conn = AsyncConnection(pg_conn)
    result = await conn.fetchval(
        JUsers.select(JUsers.name, JUsers.email)
        .aliased("users")
        .json()
    )
    assert isinstance(result, str)
    assert json.loads(result) == {"users": []}


@pytest.mark.asyncio(loop_scope="session")
async def test_json_with_where_filter(pg_conn: Any) -> None:
    """WHERE clause is applied inside the inner query before JSON wrapping."""
    conn = AsyncConnection(pg_conn)
    result = await conn.fetchval(
        JUsers.select(JUsers.name, JUsers.email)
        .where(JUsers.name == "Bob")
        .aliased("users")
        .json()
    )
    assert isinstance(result, str)
    assert json.loads(result) == {"users": [{"name": "Bob", "email": "bob@example.com"}]}
