# 04 — INSERT (single row and bulk)

Status: needs-triage
Type: AFK

## What to build

Add INSERT support for both a single-row payload and a bulk payload. Columns marked `db_default=True` or `primary_key=True` are excluded from the inserted column list by default (so callers don't have to handle server-side defaults).

UPSERT is **not** part of this slice — it ships separately in `12-upsert-on-conflict.md`.

### Usage example

```python
# single row
q = Users.insert({"name": "Alice", "email": "alice@example.com", "age": 30})
sql, params = q.build()
# sql    == INSERT INTO "accounts"."user" ("name","email","age") VALUES ($1,$2,$3)
# params == ("Alice", "alice@example.com", 30)
await conn.execute(q)

# bulk
q = Users.insert_many([
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob",   "email": "bob@example.com",   "age": 25},
])
await conn.execute(q)

# explicitly include a db_default column when needed
q = Users.insert({"id": 99, "name": "Imported", ...}, exclude_defaults=False)
```

## Acceptance criteria

- [ ] `_TableProxy.insert(data: dict[str, Any], *, exclude_defaults: bool = True)` returns a `QueryBuilder`
- [ ] `_TableProxy.insert_many(rows: list[dict[str, Any]], *, exclude_defaults: bool = True)` returns a `QueryBuilder`; raises a clear error on empty list
- [ ] By default, keys corresponding to `db_default=True` or `primary_key=True` columns are dropped from the inserted set
- [ ] `exclude_defaults=False` includes every key the caller passed
- [ ] All inserted values are bound as parameters; no literal interpolation
- [ ] `insert_many` accepts rows with a consistent column set; behavior on inconsistent column sets is documented (raise vs union — implementer's call, but documented in the issue's resolution)
- [ ] Unit tests assert SQL + params for single, bulk, and `exclude_defaults=False` cases
- [ ] End-to-end integration test inserts rows against real PostgreSQL and verifies them with a subsequent SELECT

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip
