# 06 — JOINs and table aliasing

Status: needs-triage
Type: AFK

## What to build

Support every standard join type and aliased table proxies (required for self-joins and for distinct references to the same model in one query). Join conditions are built from `FieldProxy` comparisons on both sides — no string column names.

### Usage example

```python
# Multi-table join with column aliases
Posts = table(PostModel)

q = (
    Users
    .select(
        Users.name.as_("author"),
        Posts.title.as_("post_title"),
    )
    .join(Posts, on=Users.id == Posts.user_id)
)

# Self-join via aliased table proxies
Mgr = table(EmployeeModel, alias="mgr")
Rep = table(EmployeeModel, alias="rep")

q = (
    Mgr
    .select(
        Mgr.name.as_("manager_name"),
        Rep.name.as_("report_name"),
    )
    .join(Rep, on=Mgr.id == Rep.manager_id)
)
# → SELECT mgr.name AS manager_name, rep.name AS report_name
#   FROM employees mgr JOIN employees rep ON mgr.id = rep.manager_id

# LEFT / RIGHT / CROSS variants
q = Users.select(Users.id, Posts.id).left_join(Posts, on=Users.id == Posts.user_id)
q = Users.select(Users.id, Posts.id).right_join(Posts, on=Users.id == Posts.user_id)
q = Users.select(Users.id, Posts.id).cross_join(Posts)
```

## Acceptance criteria

- [ ] `QueryBuilder.join(other, on=criterion)` — INNER JOIN
- [ ] `QueryBuilder.left_join(other, on=criterion)` — LEFT JOIN
- [ ] `QueryBuilder.right_join(other, on=criterion)` — RIGHT JOIN
- [ ] `QueryBuilder.cross_join(other)` — CROSS JOIN, no `on=` argument
- [ ] `other` may be a table proxy, an aliased table proxy, or a `SubqueryProxy` (the last one is exercised by slice 08, but the join API must already accept it)
- [ ] `table(Model, alias="...")` returns a fresh class bound to the alias (bypasses the cache) whose `FieldProxy` attributes render with the alias prefix
- [ ] Two `table(M, alias="...")` calls with the same alias produce equivalent column references
- [ ] Join conditions accept arbitrary criteria, not just single equalities (e.g. `(Mgr.id == Rep.manager_id) & (Rep.active == True)` — confirm the conjunction operator works with `FieldProxy` criteria)
- [ ] Unit tests cover each join type with at least one criterion type
- [ ] End-to-end integration test: self-join over an employee/manager fixture returns the expected manager/report pairs

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
