# 04 — INSERT (single row, bulk, and RETURNING)

Status: needs-triage
Type: AFK

## What to build

Add INSERT support for both a single-row payload and a bulk payload. Columns marked `db_default=True` or `primary_key=True` are excluded from the inserted column list by default (so callers don't have to handle server-side defaults).

Include `RETURNING` clause support on `InsertQuery` — this establishes the pattern that UPDATE and DELETE will reuse in issue 05.

UPSERT is **not** part of this slice — it ships separately in `12-upsert-on-conflict.md`.

### Usage example

```python
# single row — kwargs style
q = Users.insert(name="Alice", email="alice@example.com", age=30)
sql, params = q.build()
# sql    == INSERT INTO "public"."users" ("name","email","age") VALUES ($1,$2,$3)
# params == ("Alice", "alice@example.com", 30)
await conn.execute(q)

# bulk — list of dicts
q = Users.insert([
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob",   "email": "bob@example.com",   "age": 25},
])
await conn.execute(q)

# explicitly include a db_default column when needed
q = Users.insert(id=99, name="Imported", exclude_defaults=False)

# RETURNING — get server-generated values back
q = Users.insert(name="Alice", email="alice@example.com").returning(Users.id, Users.name)
sql, params = q.build()
# sql == INSERT INTO "public"."users" ("name","email") VALUES ($1,$2) RETURNING "users"."id","users"."name"
row  = await conn.fetch(q, UserResult)         # T | None  — single row
rows = await conn.fetch(q, list[UserResult])   # list[T]   — all rows
```

## Acceptance criteria

- [ ] `Table.insert(*, exclude_defaults: bool = True, **kwargs)` returns an `InsertQuery` (single row via kwargs)
- [ ] `Table.insert(rows: list[dict[str, Any]], *, exclude_defaults: bool = True)` returns an `InsertQuery` (bulk via list)
- [ ] Bulk `insert([])` raises a clear `ValueError` on empty list
- [ ] By default, keys corresponding to `db_default=True` or `primary_key=True` columns are dropped from the inserted set
- [ ] `exclude_defaults=False` includes every key the caller passed
- [ ] All inserted values are bound as parameters; no literal interpolation
- [ ] Bulk insert accepts rows with a consistent column set; raises `ValueError` on inconsistent column sets
- [ ] `InsertQuery.returning(*fields: Field[Any])` appends `RETURNING` to the SQL; returns a new `InsertQuery` (immutable)
- [ ] `returning()` with no arguments is a no-op (no `RETURNING` clause emitted)
- [ ] `AsyncConnection.fetch(q, ResultType)` returns `T | None`; `fetch(q, list[ResultType])` returns `list[T]`; both accept `InsertQuery` with a `RETURNING` clause
- [ ] Unit tests assert SQL + params for single, bulk, `exclude_defaults=False`, and `RETURNING` cases
- [ ] End-to-end integration test inserts a row and reads back the server-generated `id` via `RETURNING`

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip
