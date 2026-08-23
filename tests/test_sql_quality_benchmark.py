"""Offline unit tests for the categorized SQL quality benchmark harness."""

import pytest

from tests.benchmark.failure_taxonomy import (
    CATEGORIES,
    first_failing_stage,
    normalize_digits,
    normalize_identifier,
    normalize_text,
    suggest_category,
    validate_category,
)
from tests.benchmark.sql_quality_runner import (
    evaluate_case,
    load_cases,
    select_cases,
    summarize,
)


def test_categories_match_roadmap():
    assert CATEGORIES == [
        "intent", "entity", "table", "column", "filter", "value", "join",
        "aggregate", "grouping", "ranking", "result_shape", "safety", "answer",
    ]


def test_validate_category_rejects_unknown():
    with pytest.raises(ValueError):
        validate_category("unknown")


def test_normalize_digits_converts_persian_numerals():
    assert normalize_digits("۸۰ میلیون") == "80 میلیون"
    assert normalize_digits("٠١٢") == "012"


def test_normalize_text_strips_quotes_and_whitespace():
    assert normalize_text("  'دبیرستان  شهید' ") == "دبیرستان شهید"
    assert normalize_text(None) == ""


def test_normalize_identifier_removes_spaces():
    assert normalize_identifier("students.school_id = schools.id") == "students.school_id=schools.id"


def _response_with_error(stage: str, message: str, severity: str = "error"):
    return {
        "trace": {"steps": [{"name": stage, "status": "error"}]},
        "error_details": [
            {"stage": stage, "severity": severity, "message": message, "code": "test"}
        ],
    }


def test_first_failing_stage_reports_earliest_error():
    response = {
        "trace": {"steps": [
            {"name": "sql_generation", "status": "success"},
            {"name": "sql_validation", "status": "error"},
        ]},
        "error_details": [
            {"stage": "sql_validation", "severity": "error", "message": "فیلتر ضروری در SQL وجود ندارد"}
        ],
    }
    failure = first_failing_stage(response)
    assert failure is not None
    assert failure["stage"] == "sql_validation"


def test_first_failing_stage_none_when_all_ok():
    response = {"trace": {"steps": [{"name": "answer_generation", "status": "success"}]}, "error_details": []}
    assert first_failing_stage(response) is None


def test_suggest_category_filter_from_persian_message():
    category = suggest_category(
        _response_with_error("sql_validation", "فیلتر ضروری در SQL وجود ندارد: school_type=دبیرستان")
    )
    assert category == "filter"


def test_suggest_category_column_from_requested_column_message():
    category = suggest_category(
        _response_with_error("sql_validation", "ستون درخواستی کاربر در SQL وجود ندارد: students.school_type")
    )
    assert category == "column"


def test_suggest_category_falls_back_to_stage_hint():
    category = suggest_category(_response_with_error("result_shape_validation", "shape mismatch"))
    assert category == "result_shape"


def test_evaluate_case_detects_missing_required_predicate():
    case = {
        "id": "t",
        "category": "filter",
        "question": "q",
        "expected": {
            "success": True,
            "filters": [{"column": "students.first_name", "operator": "=", "value": "پوریا"}],
        },
    }
    response = {"success": True, "sql": "SELECT COUNT(*) FROM students", "result": {}}
    failures = evaluate_case(case, response)
    assert any("first_name" in f for f in failures)


def test_evaluate_case_accepts_normalized_predicate():
    case = {
        "id": "t",
        "category": "filter",
        "question": "q",
        "expected": {
            "success": True,
            "filters": [{"column": "estimated_cost", "operator": "<", "value": "80000000"}],
        },
    }
    response = {"success": True, "sql": "SELECT COUNT(*) AS c FROM demo_training_requests WHERE estimated_cost < 80000000", "result": {}}
    assert evaluate_case(case, response) == []


def test_evaluate_case_missing_table_and_join():
    case = {
        "id": "t",
        "category": "join",
        "question": "q",
        "expected": {
            "success": True,
            "tables": ["employees", "retirement_records"],
            "joins": ["retirement_records.employee_id=employees.id"],
        },
    }
    response = {"success": True, "sql": "SELECT * FROM employees", "result": {}}
    failures = evaluate_case(case, response)
    assert any(f.startswith("joins:") for f in failures)
    assert any(f.startswith("tables:") for f in failures)


def test_evaluate_case_row_count_rules():
    case = {
        "id": "t",
        "category": "aggregate",
        "question": "q",
        "expected": {"row_count_rule": "single"},
    }
    ok = evaluate_case(case, {"success": True, "sql": "SELECT 1", "result": {"rows": [{"c": 1}], "row_count": 1}})
    bad = evaluate_case(case, {"success": True, "sql": "SELECT 1", "result": {"rows": [], "row_count": 0}})
    assert ok == []
    assert bad


def test_evaluate_case_clarification_path_skips_sql_checks():
    case = {
        "id": "t",
        "category": "safety",
        "question": "q",
        "expected": {"success": False, "needs_clarification": True},
    }
    response = {"success": False, "needs_clarification": True, "sql": None, "result": None}
    assert evaluate_case(case, response) == []


def test_case_file_covers_all_categories_and_loads_cleanly():
    cases = load_cases()
    used = {case["category"] for case in cases}
    missing = set(CATEGORIES) - used
    assert not missing, f"Categories without any benchmark case: {sorted(missing)}"


def test_select_cases_by_category_and_id():
    cases = load_cases()
    filters_only = select_cases(cases, categories=["filter"])
    assert filters_only and all(c["category"] == "filter" for c in filters_only)
    one = select_cases(cases, case_ids=[cases[0]["id"]])
    assert len(one) == 1
    limited = select_cases(cases, limit=2)
    assert len(limited) == 2


def test_summarize_reports_accuracy_per_category():
    class FakeOutcome:
        def __init__(self, category, passed, stage=None):
            self.id = f"fake_{category}_{passed}"
            self.category = category
            self.passed = passed
            self.first_failing_stage = stage
            self.elapsed_ms = 1.0

    summary = summarize([FakeOutcome("filter", True), FakeOutcome("filter", False, "sql_validation")])
    assert summary["total"] == 2
    assert summary["by_category"]["filter"] == {"total": 2, "passed": 1, "failed": 1, "pass_rate": 50.0}
    assert summary["failures_by_stage"] == {"sql_validation": 1}
