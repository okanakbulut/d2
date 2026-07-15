---
title: Connection
description: "AsyncConnection, fetch / execute / fetchval, and transactions."
---

## AsyncConnection

`AsyncConnection` wraps an `asyncpg` connection and adds query-builder integration and `msgspec` deserialisation.

```python
>>> import asyncpg  # doctest: +SKIP
>>> from norm import AsyncConnection  # doctest: +SKIP
>>> raw = await asyncpg.connect("postgresql://localhost/mydb")  # doctest: +SKIP
>>> conn = AsyncConnection(raw)  # doctest: +SKIP

```

You can also pass a custom dialect (currently only `PostgresDialect` is implemented):

```python
>>> from norm.dialect import PostgresDialect  # doctest: +SKIP
>>> conn = AsyncConnection(raw, dialect=PostgresDialect())  # doctest: +SKIP

```

---

## fetch

Executes a SELECT query and deserialises the results.

### Fetch a list

```python
>>> import msgspec
>>> class UserRow(msgspec.Struct):
...     id: int
...     name: str
...
>>> rows = await conn.fetch(  # doctest: +SKIP
...     User.select(User.id, User.name),
...     list[UserRow],
... )

```

### Fetch one (or None)

```python
>>> row = await conn.fetch(  # doctest: +SKIP
...     User.select(User.id, User.name).where(User.id == 42),
...     UserRow,
... )

```

### Fetch JSON

When the query ends with `.json()`, `fetch` decodes the JSON payload and deserialises it into the result type. A JSON codec is registered on the underlying connection automatically (once per `AsyncConnection` instance):

```python
>>> class UserWithPosts(msgspec.Struct):
...     id: int
...     name: str
...     posts: list[dict]
...
>>> from norm import Table, Field, PrimaryKey, field, With  # doctest: +SKIP
>>> result = await conn.fetch(  # doctest: +SKIP
...     User.select(User.id, User.name).prefetch(
...         Post.select(Post.id, Post.title).aliased("posts")
...     ).json(),
...     list[UserWithPosts],
... )

```

---

## fetchval

Fetches a single scalar value from the first row of the result:

```python
>>> count = await conn.fetchval(  # doctest: +SKIP
...     User.select(User.id.count().aliased("n"))
... )

```

Useful for aggregates, `MAX`, `MIN`, or any query that projects a single column.

---

## execute

Executes INSERT, UPDATE, DELETE, or any write query. Returns the asyncpg command status string (e.g. `"INSERT 0 1"`):

```python
>>> status = await conn.execute(  # doctest: +SKIP
...     User.insert(username="alice", email="alice@example.com")
... )

```

---

## execute_many

Executes a bulk INSERT (when `is_many=True`, i.e. the `rows=` list form was used):

```python
>>> rows = [
...     {"username": "alice", "email": "alice@example.com"},
...     {"username": "bob",   "email": "bob@example.com"},
... ]
>>> await conn.execute_many(User.insert(rows))  # doctest: +SKIP

```

---

## transaction

Returns the underlying asyncpg transaction context manager:

```python
>>> async with conn.transaction():  # doctest: +SKIP
...     await conn.execute(User.insert(username="alice", email="alice@example.com"))
...     await conn.execute(Post.insert(user_id=1, title="Hello"))

```

If any statement inside raises, the transaction is rolled back automatically.

---

## Raw SQL access

These are intended for the migration system and should rarely be needed in application code:

```python
>>> await conn.raw_execute("TRUNCATE TABLE users")  # doctest: +SKIP
>>> await conn.raw_execute("INSERT INTO users (name) VALUES ($1)", "alice")  # doctest: +SKIP
>>> rows = await conn.raw_fetch("SELECT id, name FROM users WHERE id > $1", 0)  # doctest: +SKIP
>>> async with conn.raw_transaction():  # doctest: +SKIP
...     await conn.raw_execute("DELETE FROM users")

```

---

## Result type mapping

`fetch` uses `msgspec.convert(dict(row), result_type)` under the hood. Any type that `msgspec` can decode works:

```python
>>> class UserStruct(msgspec.Struct):
...     id: int
...     name: str
...
>>> from dataclasses import dataclass
>>> @dataclass
... class UserDC:
...     id: int
...     name: str
...

```

- `msgspec.Struct` subclasses (recommended — fastest, type-safe)
- `dict` / `list[dict]`
- `dataclasses.dataclass` instances
- Plain `TypedDict`
