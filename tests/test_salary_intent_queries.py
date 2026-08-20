from backend.pipeline.intent import extract_intent
from backend.sql.models import SQLPlan
from backend.sql.templates import render_template_sql


def test_salary_base_column_is_detected_without_forcing_average():
    intent = extract_intent("پایه حقوق کارمند با کد ملی 4871587050")
    assert intent.aggregation is None
    assert intent.requested_columns == ["base_salary"]


def test_salary_list_template_returns_requested_column():
    plan = SQLPlan(
        required_tables=["salary_items", "employees"],
        selected_columns=["SALARY_LIST", "base_salary"],
        filters=[{"column": "national_id", "operator": "=", "value": "4871587050"}],
    )
    sql = render_template_sql(plan) or ""
    assert "salary_items.base_salary" in sql
    assert "employees.national_id = '4871587050'" in sql
    assert "AVG(" not in sql


def test_salary_aggregate_uses_requested_metric_only():
    plan = SQLPlan(
        required_tables=["salary_items", "employees"],
        selected_columns=["SALARY_AGGREGATE"],
        aggregations=[{"function": "AVG", "column": "salary_items.base_salary"}],
    )
    sql = render_template_sql(plan) or ""
    assert "AVG(salary_items.base_salary) AS avg_base_salary" in sql
    assert "avg_difference" not in sql
