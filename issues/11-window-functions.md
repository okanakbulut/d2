# 11 — Window functions

Status: needs-triage
Type: AFK

## What to build

Express window-function expressions via the `FieldProxy` API: `proxy.over(*partition_by).order_by(*ordering).as_(alias)`. The chained calls produce a named `FieldProxy`-like expression usable in a SELECT list.

This slice covers the spec's "window function specification" requirement (R13). Plain (non-window) aggregations were already delivered in slice 07.

### Usage example

```python
# ROW_NUMBER() OVER (PARTITION BY name ORDER BY created_at)
row_num = (
    Users.id
    .over(Users.name)
    .order_by(Users.created_at)
    .as_("row_num")
)
q = Users.select(Users.name, row_num)
# → SELECT users.name,
#          row_number(users.id) OVER (PARTITION BY users.name ORDER BY users.created_at) AS row_num
#   FROM users

# AVG(amount) OVER (PARTITION BY user_id)
avg_per_user = (
    Orders.amount
    .avg()
    .over(Orders.user_id)
    .as_("user_avg")
)
q = Orders.select(Orders.id, avg_per_user)
```

## Acceptance criteria

- [ ] `FieldProxy.over(*partition_by: FieldProxy)` returns a `WindowSpec`-like intermediate
- [ ] `WindowSpec.order_by(*proxies: FieldProxy)` returns a new `WindowSpec`
- [ ] `WindowSpec.as_(alias)` returns a `FieldProxy`-like expression usable in `SELECT` lists
- [ ] Window expressions can be combined with aggregations from slice 07 (e.g. `.avg().over(...)`) — confirm and exercise this in tests
- [ ] Both partition and ordering arguments accept any number of `FieldProxy` instances, including zero (the empty `OVER ()` case)
- [ ] Unit tests assert SQL for: `OVER ()`, `OVER (PARTITION BY x)`, `OVER (PARTITION BY x ORDER BY y)`, and aggregation-as-window
- [ ] End-to-end integration test against real PostgreSQL: row-numbering over fixture data returns the expected ranking

## Blocked by

- 07 — Aggregations, GROUP BY, and HAVING
