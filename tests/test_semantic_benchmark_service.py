from tests.benchmark.regression import RegressionOutcome
from backend.semantic.benchmark_service import DEFAULT_CASES_PATH, semantic_benchmark_service


def _outcome(case_id: str, passed: bool) -> RegressionOutcome:
    return RegressionOutcome(
        id=case_id,
        question=f"question {case_id}",
        passed=passed,
        failures=[] if passed else ["failed"],
        elapsed_ms=10.0,
        response={},
    )


def test_semantic_benchmark_summary_passes_gate():
    summary = semantic_benchmark_service.summarize(
        [_outcome("a", True), _outcome("b", True)],
        min_pass_rate=100.0,
    )

    assert summary.total == 2
    assert summary.passed == 2
    assert summary.pass_rate == 100.0
    assert summary.gate_status == "passed"


def test_semantic_benchmark_summary_fails_gate():
    summary = semantic_benchmark_service.summarize(
        [_outcome("a", True), _outcome("b", False)],
        min_pass_rate=90.0,
    )

    assert summary.total == 2
    assert summary.failed == 1
    assert summary.pass_rate == 50.0
    assert summary.gate_status == "failed"


def test_semantic_benchmark_can_select_cases_by_id():
    cases = semantic_benchmark_service._select_cases(
        DEFAULT_CASES_PATH,
        case_ids=["reg_lowest_service_payment_001"],
    )

    assert [case["id"] for case in cases] == ["reg_lowest_service_payment_001"]
