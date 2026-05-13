# 08 — Subqueries: `as_view()` and `as_scalar()`

Status: needs-triage
Type: AFK

## What to build

A `QueryBuilder` must be promotable to a **named inline view** (`SubqueryProxy`) whose output columns are typed `FieldProxy` attributes scoped to the subquery alias. The proxy must be usable anywhere a table proxy is — in `WHERE`, `JOIN`, and `SELECT` — with no string column references.

Separately, a `QueryBuilder` must be promotable to a **scalar subquery** for use in scalar comparisons (e.g. `WHERE age > (SELECT AVG(age) FROM users)`).

`SubqueryProxy` must enforce immutability the same way `QueryBuilder` does.

### Usage example

```python
# as_view — typed inline view
revenue_by_user = (
    Orders
    .select(
        Orders.user_id,
        Orders.amount.sum().as_("total"),
    )
    .group_by(Orders.user_id)
    .as_view("rev")
)
# revenue_by_user.user_id and revenue_by_user.total are FieldProxy attributes

q = (
    Users
    .select(Users.name, revenue_by_user.total)
    .join(revenue_by_user, on=Users.id == revenue_by_user.user_id)
    .where(revenue_by_user.total > 1000)
)
# → SELECT users.name, rev.total
#   FROM users
#   JOIN (SELECT user_id, SUM(amount) AS total FROM orders GROUP BY user_id) rev
#     ON users.id = rev.user_id
#   WHERE rev.total > $1

# as_scalar — scalar subquery in a comparison
avg_age_qb = Users.select(Users.age.avg())
q = Users.select_all().where(Users.age > avg_age_qb.as_scalar())
```

## Acceptance criteria

- [ ] `QueryBuilder.as_view(alias)` returns a `SubqueryProxy` whose `FieldProxy` attributes match the columns the inner query projects
- [ ] The set of attributes on a `SubqueryProxy` is consistent with the columns named in the underlying `select(...)` / `select_all()` of the inner builder (column projections, aggregations, aliases included)
- [ ] `SubqueryProxy` raises on attribute mutation, same as `QueryBuilder`
- [ ] A `SubqueryProxy` is accepted by `QueryBuilder.join(...)` / `left_join` / `right_join` / `cross_join` from slice 06
- [ ] `SubqueryProxy.col` is usable in `.where(...)` and `.select(...)` on outer queries with the same operator surface as a regular `FieldProxy`
- [ ] `QueryBuilder.as_scalar()` returns a value usable as the right-hand side of a `FieldProxy` comparison (e.g. `Users.age > qb.as_scalar()`)
- [ ] All parameters from the inner subquery flow through to the outer query's bound parameters tuple in correct positional order
- [ ] Unit tests assert generated SQL and the parameter ordering for: subquery-as-view in JOIN, subquery-as-view in WHERE, scalar subquery in WHERE
- [ ] End-to-end integration test exercises a realistic "JOIN against a grouped subquery" pattern

## Blocked by

- 06 — JOINs and table aliasing
- 07 — Aggregations, GROUP BY, and HAVING
