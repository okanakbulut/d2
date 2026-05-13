# 12 — UPSERT (`INSERT … ON CONFLICT`)

Status: needs-triage
Type: HITL — API confirmation required before implementation

## What to build

Add UPSERT support to the INSERT path: `INSERT … ON CONFLICT (target) DO UPDATE SET …` and `INSERT … ON CONFLICT (target) DO NOTHING`. The conflict target must be expressed as a `FieldProxy` (single column or composite) — no string column names.

The design doc sketches the call site as:

```python
q = (
    Users
    .insert({"name": "Alice", "email": "alice@example.com"})
    .on_conflict(Users.email)
    .do_update(Users.name)
    .build()
)
```

…but the exact shape of `.do_update(...)` is **not yet decided**. Three competing patterns are listed below — pick one before implementation starts.

### API options to confirm

**Option A — column references only**, "update each named column to the EXCLUDED value":

```python
q = (
    Users.insert({"name": "Alice", "email": "alice@example.com"})
         .on_conflict(Users.email)
         .do_update(Users.name)           # SET name = EXCLUDED.name
)
```

Pros: trivial call site. Cons: only the "use the proposed value" pattern is expressible.

**Option B — assignments**, mirroring UPDATE:

```python
q = (
    Users.insert({"name": "Alice", "email": "alice@example.com"})
         .on_conflict(Users.email)
         .do_update(
             Users.name.set(Users.name),                       # keep existing
             Users.login_count.set(Users.login_count + 1),     # arithmetic
         )
)
```

Pros: maximally expressive — supports arithmetic and arbitrary SET RHS. Cons: no syntactic distinction between "use proposed value" vs "use existing" — needs an `excluded` helper.

**Option C — excluded helper + assignments**:

```python
from norm import excluded

q = (
    Users.insert({"name": "Alice", "email": "alice@example.com"})
         .on_conflict(Users.email)
         .do_update(
             Users.name.set(excluded(Users.name)),             # use proposed
             Users.login_count.set(Users.login_count + 1),
         )
)
```

Pros: explicit, expressive, no ambiguity. Cons: an extra import / one more concept.

**For `do_nothing`** there's no ambiguity:

```python
q = Users.insert({...}).on_conflict(Users.email).do_nothing()
```

### Usage example (once option is chosen)

A representative round-trip exercising the chosen API plus a multi-column conflict target:

```python
q = (
    Users
    .insert({"name": "Alice", "email": "alice@example.com", "tenant_id": 7})
    .on_conflict(Users.email, Users.tenant_id)   # composite target
    .do_update(...)                              # per chosen option
)
```

## Acceptance criteria

- [ ] User has confirmed which option (A / B / C) the API will adopt
- [ ] `QueryBuilder` (or whatever the post-insert object is) exposes `on_conflict(*proxies)` accepting one or more `FieldProxy` instances as the conflict target
- [ ] `do_update(...)` matches the chosen option's signature
- [ ] `do_nothing()` produces `ON CONFLICT (...) DO NOTHING`
- [ ] All literal values flow through bound parameters
- [ ] Unit tests assert SQL + params for: single-column conflict + update, composite conflict + update, `do_nothing`
- [ ] End-to-end integration test against real PostgreSQL: a duplicate insert into a unique column resolves correctly under the chosen semantics

## Blocked by

- 04 — INSERT (single row and bulk)
