# 07 — Aggregations, GROUP BY, and HAVING

Status: needs-triage
Type: AFK

## What to build

Add the aggregation surface to `FieldProxy` and the corresponding query-shape operators on `QueryBuilder`. Every aggregation returns a typed `FieldProxy` so the result can be aliased, projected, or used in a `HAVING` clause — and `HAVING` criteria are built from the same proxy API as `WHERE`, never from raw strings.

Also includes scalar functions used at SELECT/predicate level: `coalesce` and `cast`.

Window functions are **not** part of this slice — they ship in `11-window-functions.md`.

### Usage example

```python
q = (
    Users
    .select(
        Users.id.count(distinct=True).as_("unique_users"),
        Users.age.avg().as_("avg_age"),
        Users.age.max().as_("oldest"),
        Users.age.coalesce(0).as_("age_safe"),     # COALESCE(age, 0)
        Users.age.cast("float").as_("age_f"),      # CAST(age AS float)
    )
    .group_by(Users.name)
    .having(Users.id.count() > 5)
)
sql, params = q.build()
```

## Acceptance criteria

`FieldProxy`:

- [ ] `count(distinct: bool = False)` returns `FieldProxy[int]`
- [ ] `sum()`, `min()`, `max()` return `FieldProxy[T]` where `T` is the column's Python type
- [ ] `avg()` returns `FieldProxy[float]`
- [ ] `coalesce(default)` returns a `FieldProxy` of the same Python type; `default` binds as a parameter
- [ ] `cast(sql_type: str)` returns a `FieldProxy` of an opaque type (acceptable; final ergonomics revisited later)

`QueryBuilder`:

- [ ] `group_by(*proxies)` returns a new builder
- [ ] `having(criterion)` returns a new builder
- [ ] `having` accepts criteria built from aggregated `FieldProxy` instances (e.g. `Users.id.count() > 5`) — no raw strings
- [ ] Aggregated expressions remain usable inside the SELECT list, alongside non-aggregated columns when `group_by` is present

Tests:

- [ ] Unit tests assert SQL + params for each aggregation, for `group_by`, and for `having`
- [ ] End-to-end integration test: a real query against fixture data returns the expected aggregate values

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
