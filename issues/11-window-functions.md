# 11 — Window functions

Status: needs-triage
Type: AFK

## What to build

Express window-function expressions via the `FieldProxy` API: `proxy.over(*partition_by).order_by(*ordering).as_(alias)`. The chained calls produce a named `FieldProxy`-like expression usable in a SELECT list.

This slice covers the spec's "window function specification" requirement (R13). Plain (non-window) aggregations were already delivered in slice 07.

### Usage example

Source: https://www.postgresql.org/docs/current/tutorial-window.html (`empsalary` table with columns `depname`, `empno`, `salary`).

```python
# AVG(salary) OVER (PARTITION BY depname)
# → each employee row also shows the average salary for their department
avg_by_dept = (
    EmpSalary.salary
    .avg()
    .over(EmpSalary.depname)
    .as_("avg")
)
q = EmpSalary.select(EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, avg_by_dept)
# → SELECT empsalary.depname, empsalary.empno, empsalary.salary,
#          avg(empsalary.salary) OVER (PARTITION BY empsalary.depname) AS avg
#   FROM empsalary

# ROW_NUMBER() OVER (PARTITION BY depname ORDER BY salary DESC)
# → rank employees within each department by salary
row_num = (
    EmpSalary.empno
    .over(EmpSalary.depname)
    .order_by(EmpSalary.salary.desc())
    .as_("row_number")
)
q = EmpSalary.select(EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, row_num)
# → SELECT empsalary.depname, empsalary.empno, empsalary.salary,
#          row_number() OVER (PARTITION BY empsalary.depname ORDER BY empsalary.salary DESC) AS row_number
#   FROM empsalary

# SUM(salary) OVER ()  — empty window covers all rows (grand total on every row)
grand_total = (
    EmpSalary.salary
    .sum()
    .over()
    .as_("sum")
)
q = EmpSalary.select(EmpSalary.salary, grand_total)
# → SELECT empsalary.salary,
#          sum(empsalary.salary) OVER () AS sum
#   FROM empsalary

# SUM(salary) OVER (ORDER BY salary)  — running total ordered by salary
running_sum = (
    EmpSalary.salary
    .sum()
    .over()
    .order_by(EmpSalary.salary)
    .as_("sum")
)
q = EmpSalary.select(EmpSalary.salary, running_sum)
# → SELECT empsalary.salary,
#          sum(empsalary.salary) OVER (ORDER BY empsalary.salary) AS sum
#   FROM empsalary
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
