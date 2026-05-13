# 02 — Comparison predicates, column aliasing, and ordering

Status: needs-triage
Type: AFK

## What to build

Round out the SELECT-side surface so realistic read queries can be expressed end-to-end. Builds on the tracer's `FieldProxy.__eq__` and adds the rest of the column-expression and query-shape operators.

After this slice, a user can express any single-table filtered, sorted, paginated, projected query — including inequalities, string matches, list/null tests, ranges, column aliases in the SELECT output, and column-on-column arithmetic (which is also the foundation for `UPDATE col = col + 1` later).

### Usage example

```python
q = (
    Users
    .select(
        Users.name.as_("display_name"),     # column alias
        Users.age,
    )
    .where(Users.name.ilike("ali%"))        # ILIKE
    .where(Users.age.between(18, 65))       # BETWEEN
    .where(Users.email.isnotnull())         # IS NOT NULL
    .where(Users.id.isin([1, 2, 3]))        # IN
    .order_by(Users.created_at, desc=True)  # ORDER BY ... DESC
    .limit(50)
    .offset(100)
    .distinct()
)
sql, params = q.build()
# params bound positionally — no literal values in sql
```

## Acceptance criteria

`FieldProxy`:

- [ ] Comparisons: `!=`, `<`, `<=`, `>`, `>=` produce typed criteria; literal RHS values bind as parameters
- [ ] `FieldProxy == FieldProxy` (cross-column comparison) does not bind a parameter — both sides are column references
- [ ] String predicates: `like(pat)`, `ilike(pat)` — pattern is a bound parameter
- [ ] List predicates: `isin(values)`, `notin(values)` — every element bound as a parameter
- [ ] Null predicates: `isnull()`, `isnotnull()` — no parameter
- [ ] Range predicate: `between(lo, hi)` — both bounds bound as parameters
- [ ] `as_(alias)` returns a `FieldProxy` whose rendered output column is the given alias
- [ ] Arithmetic: `+`, `-`, `*`, `/` between a `FieldProxy` and a literal or another `FieldProxy`, returning a new `FieldProxy` (literal operand binds as a parameter)

`QueryBuilder`:

- [ ] `order_by(*proxies, desc=False)` — composable; multiple `order_by` calls append; ASC default, DESC opt-in
- [ ] `limit(n)`, `offset(n)`, `distinct()` — each returns a new builder
- [ ] All new builder methods preserve immutability of the original

Tests:

- [ ] Unit tests assert SQL string + params for every operator
- [ ] End-to-end integration test: a query exercising at least three predicate types, `order_by`, `limit`, `offset`, and one aliased projection returns the expected rows

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip
