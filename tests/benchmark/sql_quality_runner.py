"""Categorized SQL quality benchmark runner.

Evaluates pipeline responses against structured expectations (tables, columns,
filters, joins, ordering, result shape) from sql_quality_cases.json and reports
accuracy per failure-taxonomy category plus the first failing pipeline stage.

Usage:
    python -m tests.benchmark.sql_quality_runner            # full report
    python -m tests.benchmark.sql_quality_runner --category filter
    python -m tests.benchmark.sql_quality_runner --case-id sqlq_school_phone_by_name

Results are saved under tests/results/. The runner only issues read-only
pipeline requests and never mutates production state.

Note: predicate matching compares normalized text (digits, quotes, whitespace).
IN-list / repeated-OR equivalence is intentionally deferred to the required-
filter validator work (roadmap Change 2).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline
from tests.benchmark.failure_taxonomy import (
    CATEGORIES,
    first_failing_stage,
    normalize_identifier,
    normalize_text,
    suggest_category,
)

CASES_PATH = Path(__file__).with_name("sql_quality_cases.json")
RESULTS_DIR = Path(__file__).parents[1] / "results"

_ROW_COUNT_RULES = {"single", "at_most_one", "multiple", "any"}
_OPERATORS = {"=", "!=", "<>", ">", ">=", "<", "<="}


@dataclass
class SqlQualityOutcome:
    id: str
    question: str
    category: str
    passed: bool
    failures: list[str]
    first_failing_stage: str | None
    suggested_category: str
    elapsed_ms: float
    response: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "category": self.category,
            "passed": self.passed,
            "failures": self.failures,
            "first_failing_stage": self.first_failing_stage,
            "suggested_category": self.suggested_category,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        cases = json.load(file)
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case ids in sql_quality_cases.json")
    for case in cases:
        if case.get("category") not in CATEGORIES:
            raise ValueError(f"Case {case['id']} has invalid category {case.get('category')!r}")
    return cases


def select_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = list(cases)
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case["id"] in wanted]
    if categories:
        wanted_categories = set(categories)
        selected = [case for case in selected if case["category"] in wanted_categories]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _extract_tables(sql: str) -> set[str]:
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql, flags=re.IGNORECASE)
    return {normalize_identifier(match) for match in matches}


def _select_segment(sql: str) -> str:
    match = re.search(r"\bFROM\b", sql, flags=re.IGNORECASE)
    return sql[: match.start()] if match else sql


def _predicate_variants(column: str, operator: str, value: str) -> list[str]:
    normalized_column = normalize_identifier(column)
    normalized_value = normalize_text(value)
    base_operator = "<>" if operator == "!=" else operator
    spaced = f"{normalized_column} {base_operator} {normalized_value}"
    return [
        spaced,
        spaced.replace(" ", ""),  # tolerate compact formatting like col=val
    ]


def _column_in_select(select_segment: str, column: str) -> bool:
    normalized_segment = normalize_identifier(select_segment)
    target = normalize_identifier(column)
    if target in normalized_segment:
        return True
    short_name = target.split(".")[-1]
    return f".{short_name}" in normalized_segment


def evaluate_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    """Return a list of expectation failures; empty means the case passed."""
    expected = case.get("expected", {})
    failures: list[str] = []

    for key in ("success", "needs_clarification"):
        if key in expected and response.get(key) != expected[key]:
            failures.append(f"{key}: expected {expected[key]!r}, got {response.get(key)!r}")

    group = expected.get("group")
    if group is not None and response.get("group") != group:
        failures.append(f"group: expected {group!r}, got {response.get('group')!r}")

    operation = expected.get("operation")
    if operation is not None:
        intent_operation = ((response.get("intent") or {}).get("aggregation") or "").lower()
        if intent_operation != str(operation).lower():
            failures.append(f"operation: expected {operation!r}, got {intent_operation!r}")

    sql = response.get("sql") or ""
    needs_clarification = bool(response.get("needs_clarification"))
    has_sql = bool(sql.strip())

    if not needs_clarification and expected.get("success") and not has_sql:
        failures.append("sql: expected non-empty SQL")

    if has_sql and not needs_clarification:
        failures.extend(_evaluate_sql_expectations(expected, sql))

    failures.extend(_evaluate_result_expectations(expected, response))
    return failures


def _evaluate_sql_expectations(expected: dict[str, Any], sql: str) -> list[str]:
    failures: list[str] = []
    normalized_sql = normalize_text(sql)

    required_tables = {normalize_identifier(table) for table in expected.get("tables", [])}
    found_tables = {table for table in _extract_tables(sql)}
    missing_tables = sorted(required_tables - found_tables)
    if missing_tables:
        failures.append(f"tables: missing {missing_tables} in SQL tables {sorted(found_tables)}")

    for column in expected.get("columns", []):
        if not _column_in_select(_select_segment(sql), column):
            failures.append(f"columns: {column} not in SELECT list")

    for join in expected.get("joins", []):
        normalized_join = normalize_identifier(join)
        left, right = [part.strip() for part in join.split("=", 1)]
        variants = {
            normalized_join,
            normalize_identifier(f"{right}={left}"),
            f"{normalize_identifier(left)} {normalize_identifier(right)}",
            f"{normalize_identifier(right)} {normalize_identifier(left)}",
        }
        if not variants & {re.sub(r"\s+", "", normalized_sql)} and not _on_clause_matches(normalized_sql, left, right):
            failures.append(f"joins: no ON clause matches {join}")

    for spec in expected.get("filters", []):
        operator = spec.get("operator", "=")
        if operator not in _OPERATORS:
            failures.append(f"filters: unsupported operator {operator!r} in case definition")
            continue
        variants = _predicate_variants(spec.get("column", ""), operator, str(spec.get("value", "")))
        compact_sql = re.sub(r"\s+", "", normalized_sql)
        if not any(re.sub(r"\s+", "", variant) in compact_sql for variant in variants):
            failures.append(
                f"filters: predicate {spec.get('column')} {operator} {spec.get('value')!r} missing"
            )

    order_by = expected.get("order_by")
    if order_by:
        direction = str(order_by.get("direction", "asc")).lower()
        pattern = rf"order\s+by\s+{re.escape(normalize_identifier(order_by.get('column', '')))}"
        if not re.search(pattern, normalized_sql.replace("'", "")):
            failures.append(f"order_by: ORDER BY {order_by.get('column')} missing")
        elif direction == "asc" and not re.search(rf"{pattern}(?!\s+desc)", normalized_sql.replace("'", "")):
            failures.append("order_by: expected ascending order")
        elif direction == "desc" and "desc" not in normalized_sql.lower():
            failures.append("order_by: expected descending order")

    return failures


def _on_clause_matches(normalized_sql: str, left: str, right: str) -> bool:
    """Fallback join check: both sides of the expected equality appear in one ON clause."""
    normalized_left = normalize_identifier(left)
    normalized_right = normalize_identifier(right)
    for clause in re.findall(r"\bon\b(.+?)(?=\bjoin\b|\bwhere\b|\bgroup\b|\border\b|$)", normalized_sql, flags=re.IGNORECASE):
        compact = re.sub(r"\s+", "", clause)
        if normalized_left in compact and normalized_right in compact:
            return True
    return False


def _evaluate_result_expectations(expected: dict[str, Any], response: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    result = response.get("result") or {}
    rows = result.get("rows") or []
    row_count = int(result.get("row_count", len(rows)))

    rule = expected.get("row_count_rule")
    if rule == "single" and row_count != 1:
        failures.append(f"row_count_rule=single: got {row_count} rows")
    elif rule == "at_most_one" and row_count > 1:
        failures.append(f"row_count_rule=at_most_one: got {row_count} rows")
    elif rule == "multiple" and row_count < 1:
        failures.append("row_count_rule=multiple: got empty result")

    if "row_count" in expected and row_count != expected["row_count"]:
        failures.append(f"row_count: expected {expected['row_count']!r}, got {row_count!r}")

    actual_columns = [str(column) for column in (result.get("columns") or [])]
    lowered_actual = [column.lower() for column in actual_columns]
    for token in expected.get("result_columns", []):
        wanted = normalize_identifier(token).split(".")[-1]
        if not any(wanted == column or column.endswith(f"_{wanted}") or wanted in column for column in lowered_actual):
            failures.append(
                f"result_columns: {token} missing from executed columns {actual_columns}"
            )

    if expected.get("answer_not_empty") and not (response.get("answer") or "").strip():
        failures.append("answer: expected non-empty Persian answer")
    return failures


async def run_case(case: dict[str, Any]) -> SqlQualityOutcome:
    start = time.time()
    response_model = await query_pipeline.execute(
        PipelineRequest(question=case["question"], execute=case.get("execute", False))
    )
    elapsed_ms = (time.time() - start) * 1000
    response = response_model.model_dump(mode="json")
    failures = evaluate_case(case, response)
    stage_info = first_failing_stage(response)
    return SqlQualityOutcome(
        id=case["id"],
        question=case["question"],
        category=case["category"],
        passed=not failures,
        failures=failures,
        first_failing_stage=(stage_info or {}).get("stage"),
        suggested_category=suggest_category(response, default=case["category"]),
        elapsed_ms=elapsed_ms,
        response=response,
    )


async def run_suite(
    cases: list[dict[str, Any]] | None = None,
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int | None = None,
) -> list[SqlQualityOutcome]:
    selected = select_cases(
        cases if cases is not None else load_cases(),
        case_ids=case_ids,
        categories=categories,
        limit=limit,
    )
    outcomes = []
    for case in selected:
        outcome = await run_case(case)
        outcomes.append(outcome)
        status = "PASS" if outcome.passed else "FAIL"
        print(
            f"[{status}] {outcome.id} category={outcome.category}"
            f" stage={outcome.first_failing_stage or '-'} elapsed={outcome.elapsed_ms:.0f}ms",
            flush=True,
        )
        for failure in outcome.failures:
            print(f"    - {failure}", flush=True)
    return outcomes


def summarize(outcomes: list[SqlQualityOutcome]) -> dict[str, Any]:
    total = len(outcomes)
    passed = sum(1 for outcome in outcomes if outcome.passed)
    by_category: dict[str, dict[str, Any]] = {
        category: {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}
        for category in CATEGORIES
    }
    stage_counts: dict[str, int] = {}
    for outcome in outcomes:
        bucket = by_category.setdefault(
            outcome.category, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}
        )
        bucket["total"] += 1
        if outcome.passed:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
            if outcome.first_failing_stage:
                stage_counts[outcome.first_failing_stage] = stage_counts.get(outcome.first_failing_stage, 0) + 1
    for bucket in by_category.values():
        if bucket["total"]:
            bucket["pass_rate"] = round(bucket["passed"] / bucket["total"] * 100, 2)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "avg_elapsed_ms": round(sum(o.elapsed_ms for o in outcomes) / total, 2) if total else 0.0,
        "by_category": {k: v for k, v in by_category.items() if v["total"]},
        "failures_by_stage": dict(sorted(stage_counts.items(), key=lambda kv: kv[1], reverse=True)),
        "failed_cases": [o.id for o in outcomes if not o.passed],
    }


def save_results(outcomes: list[SqlQualityOutcome]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summarize(outcomes), "results": [o.to_dict() for o in outcomes]}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped = RESULTS_DIR / f"sql_quality_{timestamp}.json"
    latest = RESULTS_DIR / "latest_sql_quality.json"
    for path in (timestamped, latest):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return timestamped, latest


def run_sync(
    *,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int | None = None,
    save: bool = True,
) -> dict[str, Any]:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    outcomes = asyncio.run(
        run_suite(case_ids=case_ids, categories=categories, limit=limit)
    )
    summary = summarize(outcomes)
    saved_paths = save_results(outcomes) if save else (None, None)
    return {"summary": summary, "outcomes": outcomes, "saved": saved_paths}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run categorized SQL quality benchmark.")
    parser.add_argument("--case-id", action="append", dest="case_ids", default=None)
    parser.add_argument("--category", action="append", dest="categories", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    result = run_sync(
        case_ids=args.case_ids,
        categories=args.categories,
        limit=args.limit,
        save=not args.no_save,
    )
    summary = result["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    timestamped, latest = result["saved"]
    if timestamped:
        print(f"saved: {timestamped}")
        print(f"latest: {latest}")
