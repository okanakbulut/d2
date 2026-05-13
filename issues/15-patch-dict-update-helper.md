# 15 — Patch-dict → assignments helper for UPDATE

Status: needs-triage
Type: HITL — API confirmation required before implementation

## What to build

A convenience for converting a dict of `{column_name: value}` (typically the output of `msgspec.to_builtins(patch, omit_defaults=True)`) into a typed list of `Assignment` instances suitable for `_TableProxy.update(...)`.

Today (after slice 05) the call site looks like:

```python
patch = {"age": 33, "name": "Renamed"}
q = (
    Users.update(*[getattr(Users, c).set(v) for c, v in patch.items()])
         .where(Users.id == 42)
)
```

The open question is where the helper should live and what it should be named. Three options below — pick one before implementation starts.

### API options to confirm

**Option A — method on the table proxy**:

```python
patch = {"age": 33}
q = Users.update_from(patch).where(Users.id == 42)
```

Pros: most ergonomic, matches `insert(dict)` / `insert_many(list[dict])` shape. Cons: a second UPDATE entry point alongside `update(*assignments)`.

**Option B — free function returning a list of assignments**:

```python
from norm import assignments_from

patch = {"age": 33}
q = (
    Users.update(*assignments_from(Users, patch))
         .where(Users.id == 42)
)
```

Pros: composes with the existing `update(*assignments)`; no new entry point. Cons: noisier call site; one more import.

**Option C — pass a dict directly to `update()`**:

```python
patch = {"age": 33}
q = Users.update(patch).where(Users.id == 42)   # dict path
q = Users.update(Users.age.set(33))              # explicit path still works
```

Pros: one method, two shapes. Cons: overloaded signature; potential confusion at call sites.

### Acceptance criteria

- [ ] User has confirmed which option (A / B / C) the API will adopt
- [ ] Unknown keys (keys not present on the model) raise a clear error at call time, not at SQL execution time
- [ ] Values flow through bound parameters; no literal interpolation
- [ ] Helper supports an empty patch dict explicitly (raise vs. produce a no-op — implementer's call, recorded on the issue)
- [ ] Helper composes with `.where(...)` exactly like a hand-written `update(*assignments)` call
- [ ] Unit tests assert SQL + params for a representative patch and for the unknown-key error path
- [ ] End-to-end integration test against real PostgreSQL: a partial update from a `msgspec.to_builtins(patch_struct, omit_defaults=True)` dict applies only the present fields

## Blocked by

- 05 — UPDATE and DELETE
