import pytest

from tests.benchmark.regression import (
    RegressionOutcome,
    evaluate_response,
    load_regression_cases,
    select_regression_cases,
    summarize,
    run_case,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", load_regression_cases(), ids=lambda case: case["id"])
async def test_regression_case(case):
    outcome = await run_case(case)

    assert outcome.passed, "\n".join(outcome.failures)


def test_regression_case_selection_by_category_and_priority():
    cases = [
        {"id": "reg_student_count_001", "question": "q", "priority": "critical"},
        {"id": "reg_employee_profile_001", "question": "q", "priority": "normal"},
        {"id": "reg_school_phone_001", "question": "q", "priority": "critical"},
    ]

    selected = select_regression_cases(cases, categories=["student", "school"], priorities=["critical"])

    assert [case["id"] for case in selected] == ["reg_student_count_001", "reg_school_phone_001"]


def test_regression_summary_has_status_breakdowns_and_slowest_cases():
    outcomes = [
        RegressionOutcome(
            id="reg_student_count_001",
            question="q1",
            category="student",
            priority="critical",
            passed=True,
            failures=[],
            elapsed_ms=20,
            response={},
        ),
        RegressionOutcome(
            id="reg_employee_profile_001",
            question="q2",
            category="employee",
            priority="normal",
            passed=False,
            failures=["bad"],
            elapsed_ms=50,
            response={},
        ),
    ]

    summary = summarize(outcomes, min_pass_rate=80)

    assert summary["status"] == "failed"
    assert summary["pass_rate"] == 50
    assert summary["failed_cases"] == ["reg_employee_profile_001"]
    assert summary["by_category"]["student"]["passed"] == 1
    assert summary["by_priority"]["normal"]["failed"] == 1
    assert summary["slowest"][0]["id"] == "reg_employee_profile_001"


def test_regression_evaluator_checks_trace_steps_and_error_codes():
    case = {
        "id": "reg_shape_001",
        "question": "q",
        "expected": {
            "trace_steps": ["result_shape_validation"],
            "trace_step_status": {"result_shape_validation": "error"},
            "error_codes": ["result.shape_mismatch"],
        },
    }
    response = {
        "trace": {"steps": [{"name": "result_shape_validation", "status": "error"}]},
        "error_details": [{"code": "result.shape_mismatch"}],
    }

    assert evaluate_response(case, response) == []
