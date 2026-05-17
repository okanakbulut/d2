# 10 — Set operations (UNION / INTERSECT / EXCLUDE)

Status: needs-triage
Type: AFK

## What to build

Compose two `Table` or `View` query objects of compatible shape into a single query via set operators. The result is itself a selectable query object and must compose further with `order_by`, `limit`, and `offset` from slice 02.

`.union()` already exists and supports both deduplicating and duplicate-preserving modes via its `all` keyword argument. This slice adds `intersect` and `exclude`.

### Usage example

```python
adults = Users.select_all().where(Users.age >= 18)
minors = Users.select_all().where(Users.age <  18)

q = adults.union(minors).order_by(Users.name).limit(100)
# → (SELECT * FROM users WHERE age >= $1)
#   UNION
#   (SELECT * FROM users WHERE age <  $2)
#   ORDER BY name ASC
#   LIMIT 100

q = adults.union(minors, all=True)   # UNION ALL — preserves duplicates

active     = Users.select_all().where(Users.email.isnotnull())
subscribed = Users.select_all().where(Users.subscribed == True)
q = active.intersect(subscribed)

all_users = Users.select_all()
banned    = Users.select_all().where(Users.banned == True)
q = all_users.exclude(banned)
```

## Acceptance criteria

- [x] `.union(other)` — deduplicating union (already implemented)
- [x] `.union(other, all=True)` — preserves duplicates (already implemented)
- [ ] `.intersect(other)` — set intersection
- [ ] `.exclude(other)` — set difference
- [ ] Result accepts subsequent `.order_by(...)`, `.limit(...)`, `.offset(...)` from slice 02
- [ ] Parameters from both sides flow into the outer parameter tuple in correct positional order (left side first, then right)
- [ ] Behavior on shape-incompatible queries (different number/types of projected columns) is documented (raise vs. defer-to-database — implementer's call, recorded on the issue)
- [ ] Unit tests assert SQL + params for `intersect`, `exclude`, and one composed-with-`order_by` case
- [ ] End-to-end integration test exercises at least one operator against real data

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
