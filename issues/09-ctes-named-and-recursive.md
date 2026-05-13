# 09 — CTEs: named and recursive

Status: needs-triage
Type: AFK

## What to build

Support Common Table Expressions on `QueryBuilder`:

- **Named CTEs** — register a `QueryBuilder` under a name; reference its columns via a `SubqueryProxy` derived from the CTE.
- **Recursive CTEs** — combine an anchor query and a recursive step with `UNION ALL` into a `WITH RECURSIVE` expression. The recursive step references the CTE's own alias via an aliased table proxy.

CTE output columns must be referenced through the same typed-attribute interface as inline subqueries — never via strings.

### Usage example

```python
# Named CTE
recent_qb = Posts.select_all().where(Posts.created_at >= "2024-01-01")
RecentPosts = recent_qb.as_view("recent_posts")

q = (
    Users
    .select(Users.name, RecentPosts.title)
    .with_cte("recent_posts", recent_qb)
    .join(RecentPosts, on=Users.id == RecentPosts.user_id)
)
# → WITH recent_posts AS (SELECT * FROM posts WHERE created_at >= $1)
#   SELECT users.name, recent_posts.title
#   FROM users JOIN recent_posts ON users.id = recent_posts.user_id

# Recursive CTE — org chart
Emp    = table(EmployeeModel)
EmpCTE = table(EmployeeModel, alias="org_cte")

anchor = (
    Emp.select(Emp.id, Emp.name, Emp.manager_id)
       .where(Emp.manager_id.isnull())
)
step = (
    Emp.select(Emp.id, Emp.name, Emp.manager_id)
       .join(EmpCTE, on=Emp.manager_id == EmpCTE.id)
)
q = (
    Emp
    .select_all()
    .with_recursive_cte("org_cte", anchor=anchor, recursive=step)
)
# → WITH RECURSIVE org_cte AS (
#       SELECT id, name, manager_id FROM employees WHERE manager_id IS NULL
#       UNION ALL
#       SELECT e.id, e.name, e.manager_id
#       FROM employees e JOIN org_cte ON e.manager_id = org_cte.id
#   )
#   SELECT * FROM employees
```

## Acceptance criteria

- [ ] `QueryBuilder.with_cte(name, cte_qb)` returns a new builder with the CTE registered; the rendered query begins with `WITH <name> AS (...)`
- [ ] `QueryBuilder.with_recursive_cte(name, *, anchor, recursive)` produces `WITH RECURSIVE <name> AS (anchor UNION ALL recursive)`
- [ ] Multiple `with_cte` registrations on the same builder are supported and rendered in order
- [ ] CTE output columns are accessed via a `SubqueryProxy`-like typed attribute interface (no raw strings); the recursive step accesses the CTE's own columns via `table(Model, alias="<cte_name>")`
- [ ] Parameters from the CTE inner query flow into the outer parameter tuple in correct positional order
- [ ] Unit tests assert SQL + params for: single named CTE, two named CTEs, a recursive CTE
- [ ] End-to-end integration test against real PostgreSQL: a recursive CTE over an employee/manager fixture returns the full subtree under a chosen root

## Blocked by

- 08 — Subqueries: `as_view()` and `as_scalar()`
