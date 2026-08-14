from decimal import Decimal

from backend.pipeline.intent import NormalizedIntent
from backend.sql.models import SQLPlan
from backend.sql.result_shape_validator import sql_result_shape_validator


def test_result_shape_accepts_count_single_numeric_row():
    result = {
        "columns": ["student_count"],
        "rows": [{"student_count": Decimal("285082")}],
        "row_count": 1,
    }
    normalized = NormalizedIntent(entity="student", operation="count", confidence=0.9)

    shape = sql_result_shape_validator.verify(result, normalized)

    assert shape.is_valid is True
    assert shape.expected_single_row is True
    assert shape.expected_numeric_value is True


def test_result_shape_rejects_count_returning_raw_rows():
    result = {
        "columns": ["id", "first_name", "last_name"],
        "rows": [
            {"id": 1, "first_name": "pouria", "last_name": "mohammadi"},
            {"id": 2, "first_name": "parsa", "last_name": "abdollahi"},
        ],
        "row_count": 2,
    }
    normalized = NormalizedIntent(entity="student", operation="count", confidence=0.9)

    shape = sql_result_shape_validator.verify(result, normalized)

    assert shape.is_valid is False
    assert any("exactly 1" in error for error in shape.errors)
    assert any("raw entity rows" in error for error in shape.errors)


def test_result_shape_rejects_profile_returning_only_count():
    result = {
        "columns": ["row_count"],
        "rows": [{"row_count": 47}],
        "row_count": 1,
    }
    normalized = NormalizedIntent(entity="school", operation="profile", confidence=0.9)

    shape = sql_result_shape_validator.verify(result, normalized)

    assert shape.is_valid is False
    assert any("count value" in error for error in shape.errors)


def test_result_shape_rejects_grouped_result_without_dimension_column():
    result = {
        "columns": ["student_count"],
        "rows": [{"student_count": 10}],
        "row_count": 1,
    }
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        dimensions=["province"],
        confidence=0.9,
    )

    shape = sql_result_shape_validator.verify(result, normalized)

    assert shape.is_valid is False
    assert any("province" in error for error in shape.errors)


def test_result_shape_warns_for_missing_requested_columns():
    result = {
        "columns": ["first_name", "last_name"],
        "rows": [{"first_name": "nasrin", "last_name": "hashemi"}],
        "row_count": 1,
    }
    normalized = NormalizedIntent(
        entity="employee",
        operation="lookup",
        requested_columns=["national_id"],
        confidence=0.9,
    )

    shape = sql_result_shape_validator.verify(result, normalized)

    assert shape.is_valid is True
    assert shape.missing_requested_columns == ["national_id"]
    assert shape.warnings


def test_result_shape_rejects_rank_one_returning_multiple_rows():
    result = {
        "columns": ["id", "pension_amount"],
        "rows": [{"id": 1, "pension_amount": 10}, {"id": 2, "pension_amount": 20}],
        "row_count": 2,
    }
    normalized = NormalizedIntent(entity="employee", operation="rank_one", confidence=0.9)
    plan = SQLPlan(required_tables=["employees"], selected_columns=["id", "pension_amount"], limit=1)

    shape = sql_result_shape_validator.verify(result, normalized, plan)

    assert shape.is_valid is False
    assert any("rank_one" in error for error in shape.errors)
    assert any("plan limit" in error for error in shape.errors)
