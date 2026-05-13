# 03 — Async execution variants and transaction passthrough

Status: needs-triage
Type: AFK

## What to build

Round out `AsyncConnection` so callers can fetch single rows, scalar values, run write statements, and group operations into a transaction. The transaction API is a thin passthrough to the underlying driver — no library-owned retry/savepoint abstraction in v1.

### Usage example

```python
conn = AsyncConnection(asyncpg_conn)

# single optional row
user: UserResult | None = await conn.fetch_one(
    Users.select_all().where(Users.id == 42),
    UserResult,
)

# scalar
total: int = await conn.fetch_val(
    Users.select(Users.id.count()).where(Users.age >= 18)
)

# write — returns driver status string (e.g. "INSERT 0 3")
status = await conn.execute(
    Users.insert({"name": "Alice", "email": "a@x.com"})
)

# transaction — driver-native context manager
async with conn.transaction():
    await conn.execute(q1)
    await conn.execute(q2)
```

## Acceptance criteria

- [ ] `fetch_one(qb, ResultStruct)` returns `ResultStruct | None` — `None` when no row matched
- [ ] `fetch_val(qb)` returns the first column of the first row, or `None`
- [ ] `execute(qb)` returns whatever the driver returns for a non-fetching statement (status string for asyncpg)
- [ ] `execute_many(qb)` — bound to bulk-insert-style operations where the same SQL runs against multiple parameter rows
- [ ] `transaction()` returns the driver's native transaction context manager, usable as `async with conn.transaction(): ...`
- [ ] No new abstractions are introduced beyond what the driver exposes (no retry helpers, no savepoint wrappers)
- [ ] All four fetch/execute paths bind parameters via the standard `(sql, params)` returned by `QueryBuilder.build()`
- [ ] Unit tests use a fake/in-memory connection mock to assert each path calls the right driver method with the right `(sql, params)`
- [ ] End-to-end integration test demonstrates a successful transaction commit and a rolled-back transaction (by raising inside the block)

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip
