from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


CASES_PATH = Path(__file__).with_name("regression_cases.json")
RESULTS_DIR = Path(__file__).parents[1] / "results"


@dataclass
class RegressionOutcome:
    id: str
    question: str
    category: str
    priority: str
    passed: bool
    failures: list[str]
    elapsed_ms: float
    response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "category": self.category,
            "priority": self.priority,
            "passed": self.passed,
            "failures": self.failures,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "response": self.response,
        }


def load_regression_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def case_category(case: dict[str, Any]) -> str:
    explicit = case.get("category")
    if explicit:
        return str(explicit)
    case_id = str(case.get("id", ""))
    if case_id.startswith("reg_student_"):
        return "student"
    if case_id.startswith("reg_employee_"):
        return "employee"
    if case_id.startswith("reg_school_"):
        return "school"
    if case_id.startswith("reg_training_"):
        return "training_request"
    if case_id.startswith("reg_semantic_"):
        return "semantic"
    if "count" in case_id:
        return "aggregate"
    return "general"


def case_priority(case: dict[str, Any]) -> str:
    explicit = case.get("priority")
    if explicit:
        return str(explicit)
    case_id = str(case.get("id", ""))
    if any(token in case_id for token in ["national_id", "pension", "count", "profile"]):
        return "critical"
    return "normal"


def select_regression_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    priorities: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = list(cases)
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case.get("id") in wanted]
    if categories:
        wanted_categories = set(categories)
        selected = [case for case in selected if case_category(case) in wanted_categories]
    if priorities:
        wanted_priorities = set(priorities)
        selected = [case for case in selected if case_priority(case) in wanted_priorities]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _value_at(data: dict[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _compare_expected_dict(actual: dict[str, Any], expected: dict[str, Any], prefix: str) -> list[str]:
    failures = []
    for key, expected_value in expected.items():
        actual_value = _value_at(actual, key)
        if (
            isinstance(actual_value, str)
            and actual_value.startswith("***")
            and isinstance(expected_value, (str, int))
            and str(actual_value[3:]) == str(expected_value)[-len(actual_value[3:]):]
        ):
            continue
        if actual_value != expected_value:
            failures.append(f"{prefix}.{key}: expected {expected_value!r}, got {actual_value!r}")
    return failures


def evaluate_response(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    expected = case.get("expected", {})
    failures: list[str] = []

    for key in ["success", "group", "report", "valid", "rejected", "unsupported", "needs_clarification"]:
        if key in expected and response.get(key) != expected[key]:
            failures.append(f"{key}: expected {expected[key]!r}, got {response.get(key)!r}")

    sql = response.get("sql") or ""
    for snippet in expected.get("sql_contains", []):
        if snippet not in sql:
            failures.append(f"sql missing snippet: {snippet}")
    for snippet in expected.get("sql_not_contains", []):
        if snippet in sql:
            failures.append(f"sql forbidden snippet present: {snippet}")

    if "intent" in expected:
        failures.extend(_compare_expected_dict(response.get("intent") or {}, expected["intent"], "intent"))

    result = response.get("result") or {}
    rows = result.get("rows") or []
    if "row_count" in expected:
        actual_count = result.get("row_count", len(rows) if rows else 0)
        if actual_count != expected["row_count"]:
            failures.append(f"row_count: expected {expected['row_count']!r}, got {actual_count!r}")

    if "first_row" in expected:
        if not rows:
            failures.append("first_row: expected at least one row, got none")
        else:
            failures.extend(_compare_expected_dict(rows[0], expected["first_row"], "first_row"))

    trace_steps = response.get("trace", {}).get("steps", [])
    trace_by_name = {
        step.get("name"): step
        for step in trace_steps
        if isinstance(step, dict) and step.get("name")
    }
    for expected_step in expected.get("trace_steps", []):
        if expected_step not in trace_by_name:
            failures.append(f"trace missing step: {expected_step}")

    for key, expected_value in expected.get("trace_step_status", {}).items():
        actual_step = trace_by_name.get(key) or {}
        actual_status = actual_step.get("status")
        if actual_status != expected_value:
            failures.append(f"trace.{key}.status: expected {expected_value!r}, got {actual_status!r}")

    for error_code in expected.get("error_codes", []):
        actual_codes = [item.get("code") for item in response.get("error_details", []) if isinstance(item, dict)]
        if error_code not in actual_codes:
            failures.append(f"error_details missing code: {error_code}")

    return failures


async def run_case(case: dict[str, Any]) -> RegressionOutcome:
    start = time.time()
    response = await query_pipeline.execute(
        PipelineRequest(question=case["question"], execute=case.get("execute", False))
    )
    elapsed_ms = (time.time() - start) * 1000
    response_dict = response.model_dump(mode="json")
    failures = evaluate_response(case, response_dict)
    return RegressionOutcome(
        id=case["id"],
        question=case["question"],
        category=case_category(case),
        priority=case_priority(case),
        passed=not failures,
        failures=failures,
        elapsed_ms=elapsed_ms,
        response=response_dict,
    )


async def run_regression_suite(
    cases: list[dict[str, Any]] | None = None,
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    priorities: list[str] | None = None,
    limit: int | None = None,
) -> list[RegressionOutcome]:
    selected_cases = select_regression_cases(
        cases or load_regression_cases(),
        case_ids=case_ids,
        categories=categories,
        priorities=priorities,
        limit=limit,
    )
    outcomes = []
    for case in selected_cases:
        outcomes.append(await run_case(case))
    return outcomes


def summarize(outcomes: list[RegressionOutcome], min_pass_rate: float = 100.0) -> dict[str, Any]:
    total = len(outcomes)
    passed = sum(1 for outcome in outcomes if outcome.passed)
    pass_rate = round((passed / total * 100), 2) if total else 0.0
    by_category: dict[str, dict[str, Any]] = {}
    by_priority: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        for bucket, key in [(by_category, outcome.category), (by_priority, outcome.priority)]:
            item = bucket.setdefault(key, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
            item["total"] += 1
            item["passed"] += 1 if outcome.passed else 0
            item["failed"] += 0 if outcome.passed else 1
    for bucket in [by_category, by_priority]:
        for item in bucket.values():
            item["pass_rate"] = round(item["passed"] / item["total"] * 100, 2) if item["total"] else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "min_pass_rate": min_pass_rate,
        "status": "passed" if pass_rate >= min_pass_rate else "failed",
        "avg_elapsed_ms": round(sum(outcome.elapsed_ms for outcome in outcomes) / total, 2) if total else 0.0,
        "slowest": [
            {
                "id": outcome.id,
                "elapsed_ms": round(outcome.elapsed_ms, 2),
                "category": outcome.category,
                "priority": outcome.priority,
            }
            for outcome in sorted(outcomes, key=lambda item: item.elapsed_ms, reverse=True)[:5]
        ],
        "failed_cases": [outcome.id for outcome in outcomes if not outcome.passed],
        "by_category": by_category,
        "by_priority": by_priority,
    }


def save_results(outcomes: list[RegressionOutcome], min_pass_rate: float = 100.0) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize(outcomes, min_pass_rate=min_pass_rate),
        "results": [outcome.to_dict() for outcome in outcomes],
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped = RESULTS_DIR / f"regression_{timestamp}.json"
    latest = RESULTS_DIR / "latest_regression.json"
    for path in [timestamped, latest]:
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    return timestamped, latest


def run_sync(
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    priorities: list[str] | None = None,
    limit: int | None = None,
) -> list[RegressionOutcome]:
    return asyncio.run(
        run_regression_suite(
            case_ids=case_ids,
            categories=categories,
            priorities=priorities,
            limit=limit,
        )
    )


if __name__ == "__main__":
    results = run_sync()
    summary = summarize(results)
    timestamped, latest = save_results(results)
    print(f"Regression: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']}%)")
    for outcome in results:
        status = "PASS" if outcome.passed else "FAIL"
        print(f"[{status}] {outcome.id} ({outcome.elapsed_ms:.0f} ms)")
        for failure in outcome.failures:
            print(f"  - {failure}")
    print(f"Saved: {timestamped}")
    print(f"Latest: {latest}")
