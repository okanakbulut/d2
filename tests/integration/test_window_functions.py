# pyright: basic
"""Integration tests for window functions against a live PostgreSQL instance."""

from typing import Any

import msgspec
import pytest

from d2 import AsyncConnection
from d2 import TableMeta, Table, Field


class EmpSalary(Table):
    __meta__ = TableMeta(table="empsalary", schema="public")
    depname: Field[str]
    empno:   Field[int]
    salary:  Field[int]


class EmpRow(msgspec.Struct):
    depname: str
    empno: int
    salary: int
    avg: float


class EmpRowNumber(msgspec.Struct):
    depname: str
    empno: int
    salary: int
    row_number: int


class SalaryWithTotal(msgspec.Struct):
    salary: int
    sum: int


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True, scope="module")
async def empsalary_table(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.empsalary (
            depname TEXT NOT NULL,
            empno   INT  NOT NULL,
            salary  INT  NOT NULL
        )
    """)
    await pg_conn.execute("DELETE FROM public.empsalary")
    rows = [
        ("develop", 11, 5200),
        ("develop", 7,  4200),
        ("develop", 9,  4500),
        ("develop", 8,  6000),
        ("develop", 10, 5200),
        ("personnel", 5, 3500),
        ("personnel", 2, 3900),
        ("sales", 3, 4800),
        ("sales", 1, 5000),
        ("sales", 4, 4800),
    ]
    for depname, empno, salary in rows:
        await pg_conn.execute(
            "INSERT INTO public.empsalary (depname, empno, salary) VALUES ($1, $2, $3)",
            depname, empno, salary,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_avg_over_partition_by_depname(pg_conn: Any) -> None:
    """AVG(salary) OVER (PARTITION BY depname) adds dept avg to every row."""
    avg_by_dept = (
        EmpSalary.salary
        .avg()
        .over(EmpSalary.depname)
        .aliased("avg")
    )
    q = EmpSalary.select(
        EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, avg_by_dept
    )
    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[EmpRow])

    develop_rows = [r for r in results if r.depname == "develop"]
    assert all(r.avg == pytest.approx(5020.0) for r in develop_rows)

    personnel_rows = [r for r in results if r.depname == "personnel"]
    assert all(r.avg == pytest.approx(3700.0) for r in personnel_rows)

    sales_rows = [r for r in results if r.depname == "sales"]
    assert all(r.avg == pytest.approx(4866.666_666, rel=1e-4) for r in sales_rows)


@pytest.mark.asyncio(loop_scope="session")
async def test_row_number_over_partition_by_depname_order_by_salary_desc(pg_conn: Any) -> None:
    """ROW_NUMBER() OVER (PARTITION BY depname ORDER BY salary DESC) ranks within dept."""
    row_num = (
        EmpSalary.empno
        .over(EmpSalary.depname)
        .order_by(EmpSalary.salary.desc())
        .aliased("row_number")
    )
    q = EmpSalary.select(
        EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, row_num
    )
    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[EmpRowNumber])

    # empno=8 has salary=6000 → rank 1 in develop
    emp8 = next(r for r in results if r.empno == 8)
    assert emp8.row_number == 1

    # empno=7 has salary=4200 → rank 5 (lowest) in develop
    emp7 = next(r for r in results if r.empno == 7)
    assert emp7.row_number == 5

    # empno=2 has salary=3900 → rank 1 in personnel (highest there)
    emp2 = next(r for r in results if r.empno == 2)
    assert emp2.row_number == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_sum_over_empty_window_grand_total(pg_conn: Any) -> None:
    """SUM(salary) OVER () attaches the grand total to every row."""
    grand_total = (
        EmpSalary.salary
        .sum()
        .over()
        .aliased("sum")
    )
    q = EmpSalary.select(EmpSalary.salary, grand_total)
    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[SalaryWithTotal])

    expected_total = sum(s for _, _, s in [
        ("develop", 11, 5200), ("develop", 7, 4200), ("develop", 9, 4500),
        ("develop", 8, 6000), ("develop", 10, 5200),
        ("personnel", 5, 3500), ("personnel", 2, 3900),
        ("sales", 3, 4800), ("sales", 1, 5000), ("sales", 4, 4800),
    ])
    assert all(r.sum == expected_total for r in results)


@pytest.mark.asyncio(loop_scope="session")
async def test_sum_over_order_by_salary_running_total(pg_conn: Any) -> None:
    """SUM(salary) OVER (ORDER BY salary) produces an ascending running total."""
    running_sum = (
        EmpSalary.salary
        .sum()
        .over()
        .order_by(EmpSalary.salary)
        .aliased("sum")
    )
    q = EmpSalary.select(EmpSalary.salary, running_sum)
    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[SalaryWithTotal])

    # Running total must be non-decreasing
    assert results == sorted(results, key=lambda r: r.sum)

    # Largest running total equals the grand total
    grand_total = sum(s for _, _, s in [
        ("develop", 11, 5200), ("develop", 7, 4200), ("develop", 9, 4500),
        ("develop", 8, 6000), ("develop", 10, 5200),
        ("personnel", 5, 3500), ("personnel", 2, 3900),
        ("sales", 3, 4800), ("sales", 1, 5000), ("sales", 4, 4800),
    ])
    assert results[-1].sum == grand_total
