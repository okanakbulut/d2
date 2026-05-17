"""Unit tests for window function SQL generation."""

from .conftest import EmpSalary


class TestAvgOverPartitionBy:
    def test_avg_over_partition_by_emits_correct_sql(self):
        avg_by_dept = (
            EmpSalary.salary
            .avg()
            .over(EmpSalary.depname)
            .aliased("avg")
        )
        sql, params = EmpSalary.select(
            EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, avg_by_dept
        ).build()

        assert sql == (
            'SELECT "empsalary"."depname",'
            '"empsalary"."empno",'
            '"empsalary"."salary",'
            'AVG("empsalary"."salary") OVER(PARTITION BY "empsalary"."depname") "avg" '
            'FROM "public"."empsalary"'
        )
        assert params == ()


class TestRowNumberOverPartitionByOrderBy:
    def test_row_number_over_partition_order_desc_emits_correct_sql(self):
        row_num = (
            EmpSalary.empno
            .over(EmpSalary.depname)
            .order_by(EmpSalary.salary.desc())
            .aliased("row_number")
        )
        sql, params = EmpSalary.select(
            EmpSalary.depname, EmpSalary.empno, EmpSalary.salary, row_num
        ).build()

        assert sql == (
            'SELECT "empsalary"."depname",'
            '"empsalary"."empno",'
            '"empsalary"."salary",'
            'ROW_NUMBER() OVER(PARTITION BY "empsalary"."depname" ORDER BY "empsalary"."salary" DESC) "row_number" '
            'FROM "public"."empsalary"'
        )
        assert params == ()


class TestSumOverEmpty:
    def test_sum_over_empty_window_emits_correct_sql(self):
        grand_total = (
            EmpSalary.salary
            .sum()
            .over()
            .aliased("sum")
        )
        sql, params = EmpSalary.select(EmpSalary.salary, grand_total).build()

        assert sql == (
            'SELECT "empsalary"."salary",'
            'SUM("empsalary"."salary") OVER() "sum" '
            'FROM "public"."empsalary"'
        )
        assert params == ()


class TestSumOverOrderBy:
    def test_sum_over_order_by_emits_running_total_sql(self):
        running_sum = (
            EmpSalary.salary
            .sum()
            .over()
            .order_by(EmpSalary.salary)
            .aliased("sum")
        )
        sql, params = EmpSalary.select(EmpSalary.salary, running_sum).build()

        assert sql == (
            'SELECT "empsalary"."salary",'
            'SUM("empsalary"."salary") OVER(ORDER BY "empsalary"."salary") "sum" '
            'FROM "public"."empsalary"'
        )
        assert params == ()


class TestWindowSpecImmutability:
    def test_order_by_returns_new_window_spec(self):
        base = EmpSalary.salary.sum().over()
        ordered = base.order_by(EmpSalary.salary)
        assert base is not ordered

    def test_chaining_does_not_mutate_base(self):
        base = EmpSalary.salary.avg().over(EmpSalary.depname)
        base.order_by(EmpSalary.salary)
        sql, _ = EmpSalary.select(base.aliased("avg")).build()
        assert "ORDER BY" not in sql
