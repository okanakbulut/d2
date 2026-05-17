# 12 — UPSERT (`INSERT … ON CONFLICT`)

Status: ready
Type: implementation

## What to build

Add UPSERT support to the INSERT path: `INSERT … ON CONFLICT (target) DO UPDATE SET …` and `INSERT … ON CONFLICT (target) DO NOTHING`. The conflict target must be expressed as one or more `FieldProxy` instances (single column or composite) — no string column names.

## API (confirmed)

### Single-row insert

```python
from norm import excluded

Users.insert(name="Alice", email="alice@example.com")
     .on_conflict(Users.email)
     .do_update(name=excluded(Users.name))
```

### Bulk insert

```python
Users.insert([
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob",   "email": "bob@example.com"},
])
.on_conflict(Users.email)
.update(name=excluded(Users.name))
```

### Composite conflict target

```python
Users.insert(name="Alice", email="alice@example.com", tenant_id=7)
     .on_conflict(Users.email, Users.tenant_id)
     .do_update(name=excluded(Users.name))
```

### Mixed update expressions

```python
Users.insert(name="Alice", email="alice@example.com", login_count=1)
     .on_conflict(Users.email)
     .update(
         name=excluded(Users.name),          # SET name = EXCLUDED.name
         login_count=Users.login_count + 1,  # SET login_count = login_count + 1
     )
```

### Do nothing

```python
Users.insert(name="Alice", email="alice@example.com")
     .on_conflict(Users.email)
     .do_nothing()
```

## Design notes

- `.do_update(**kwargs)` — keys are column names (strings), values are either literals (bound as parameters) or expressions (`FieldProxy`, arithmetic, `excluded(...)`).
- `excluded(proxy)` — wraps a `FieldProxy` to render as `EXCLUDED.<column>` in SQL. Exported from `norm`.
- `.on_conflict(*proxies)` — accepts one or more `FieldProxy` instances as the composite conflict target.
- PostgreSQL's `EXCLUDED` is a per-row virtual table, so `excluded()` works correctly across all rows in a bulk insert automatically.
- `.do_nothing()` and `.do_update(...)` are mutually exclusive terminal methods on the conflict builder.

## Acceptance criteria

- [x] `InsertQuery` exposes `.on_conflict(*proxies)` returning a conflict builder
- [x] Conflict builder exposes `.do_update(**kwargs)` where values may be literals, `FieldProxy` expressions, or `excluded(proxy)`
- [x] Conflict builder exposes `.do_nothing()` producing `ON CONFLICT (...) DO NOTHING`
- [x] `excluded(proxy)` is importable from `norm` and renders as `EXCLUDED.<column>`
- [x] All literal values flow through bound parameters
- [x] Works identically for single-row (kwargs) and bulk (list-of-dicts) inserts
- [x] Unit tests assert full SQL strings + params for:
  - single-column conflict + `.update()` with literal value
  - single-column conflict + `.update()` with `excluded()`
  - single-column conflict + `.update()` with arithmetic expression
  - composite conflict target
  - `.do_nothing()`
  - bulk insert + `.on_conflict().update()`
- [x] Integration test against real PostgreSQL: duplicate insert into a unique column resolves correctly for both `.update()` and `.do_nothing()`

## Blocked by

- 04 — INSERT (single row and bulk)
