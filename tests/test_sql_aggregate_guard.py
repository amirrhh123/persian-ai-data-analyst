from backend.pipeline.intent import IntentSorting, NormalizedIntent
from backend.sql.aggregate_guard import sql_aggregate_safety_guard
from backend.sql.models import SQLPlan


def test_aggregate_guard_accepts_count_plan():
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )
    normalized = NormalizedIntent(entity="student", operation="count", confidence=0.9)

    result = sql_aggregate_safety_guard.verify(plan, normalized)

    assert result.is_valid is True


def test_aggregate_guard_rejects_count_without_count():
    plan = SQLPlan(required_tables=["students"], selected_columns=["GENERIC_TABLE_LIST"])
    normalized = NormalizedIntent(entity="student", operation="count", confidence=0.9)

    result = sql_aggregate_safety_guard.verify(plan, normalized)

    assert result.is_valid is False
    assert any("COUNT" in error for error in result.errors)


def test_aggregate_guard_rejects_list_with_count_template():
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )
    normalized = NormalizedIntent(entity="student", operation="list", confidence=0.9)

    result = sql_aggregate_safety_guard.verify(plan, normalized)

    assert result.is_valid is False
    assert any("must not use COUNT" in error for error in result.errors)


def test_aggregate_guard_rejects_grouped_count_without_group_by():
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        dimensions=["province"],
        confidence=0.9,
    )

    result = sql_aggregate_safety_guard.verify(plan, normalized)

    assert result.is_valid is False
    assert result.requires_group_by is True
    assert any("GROUP BY" in error for error in result.errors)


def test_aggregate_guard_rejects_rank_one_without_order_and_limit():
    plan = SQLPlan(required_tables=["students"], selected_columns=["GENERIC_TABLE_LIST"])
    normalized = NormalizedIntent(
        entity="student",
        operation="rank_one",
        sort=IntentSorting(column="students.created_at", direction="DESC"),
        confidence=0.9,
    )

    result = sql_aggregate_safety_guard.verify(plan, normalized)

    assert result.is_valid is False
    assert result.requires_order_by is True
    assert result.requires_limit is True
    assert any("ORDER BY" in error for error in result.errors)
    assert any("LIMIT" in error for error in result.errors)
