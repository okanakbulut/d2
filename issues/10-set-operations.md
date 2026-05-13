# 10 — Set operations (UNION / UNION ALL / INTERSECT / EXCEPT)

Status: needs-triage
Type: AFK

## What to build

Compose two `QueryBuilder` instances of compatible shape into a single query via set operators. The result is itself a `QueryBuilder` and must compose further with `order_by`, `limit`, and `offset` from slice 02.

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

q = adults.union_all(minors)

active     = Users.select_all().where(Users.email.isnotnull())
subscribed = Users.select_all().where(Users.subscribed == True)
q = active.intersect(subscribed)

all_users = Users.select_all()
banned    = Users.select_all().where(Users.banned == True)
q = all_users.except_(banned)
```

## Acceptance criteria

- [ ] `QueryBuilder.union(other)` — deduplicating union
- [ ] `QueryBuilder.union_all(other)` — preserves duplicates
- [ ] `QueryBuilder.intersect(other)` — set intersection
- [ ] `QueryBuilder.except_(other)` — set difference (trailing underscore because `except` is a keyword)
- [ ] Result is a `QueryBuilder` and accepts subsequent `.order_by(...)`, `.limit(...)`, `.offset(...)` from slice 02
- [ ] Parameters from both sides flow into the outer parameter tuple in correct positional order (left side first, then right)
- [ ] Behavior on shape-incompatible queries (different number/types of projected columns) is documented (raise vs. defer-to-database — implementer's call, recorded on the issue)
- [ ] Unit tests assert SQL + params for each of the four operators and one composed-with-`order_by` case
- [ ] End-to-end integration test exercises at least one operator against real data

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
