import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.config import get_settings
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.models import (
    SemanticBenchmarkCaseResult,
    SemanticBenchmarkResponse,
    SemanticBenchmarkSummary,
)
from tests.benchmark.regression import (
    RegressionOutcome,
    load_regression_cases,
    run_regression_suite,
)


RESULTS_DIR = Path(__file__).parent.parent.parent / "tests" / "results"
DEFAULT_CASES_PATH = Path(__file__).parent.parent.parent / "tests" / "benchmark" / "regression_cases.json"


class SemanticBenchmarkService:
    def __init__(self):
        self.settings = get_settings()

    def _source_fingerprint(self, tenant_id: str) -> str:
        try:
            suggestions = semantic_activation_service.load_suggestions(tenant_id)
            return suggestions.source_fingerprint
        except Exception:
            return ""

    def _select_cases(
        self,
        cases_path: Path,
        case_ids: Optional[list[str]] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        cases = load_regression_cases(cases_path)
        if case_ids:
            allowed = set(case_ids)
            cases = [case for case in cases if case.get("id") in allowed]
        if limit is not None:
            cases = cases[:limit]
        return cases

    def summarize(
        self,
        outcomes: list[RegressionOutcome],
        min_pass_rate: float = 95.0,
    ) -> SemanticBenchmarkSummary:
        total = len(outcomes)
        passed = sum(1 for outcome in outcomes if outcome.passed)
        pass_rate = round((passed / total * 100), 2) if total else 0.0
        avg_elapsed_ms = round(sum(outcome.elapsed_ms for outcome in outcomes) / total, 2) if total else 0.0
        return SemanticBenchmarkSummary(
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=pass_rate,
            avg_elapsed_ms=avg_elapsed_ms,
            min_pass_rate=min_pass_rate,
            gate_status="passed" if pass_rate >= min_pass_rate else "failed",
        )

    def _case_result(self, outcome: RegressionOutcome) -> SemanticBenchmarkCaseResult:
        return SemanticBenchmarkCaseResult(
            id=outcome.id,
            question=outcome.question,
            passed=outcome.passed,
            failures=outcome.failures,
            elapsed_ms=round(outcome.elapsed_ms, 2),
        )

    def save_response(self, response: SemanticBenchmarkResponse) -> tuple[Path, Path]:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped = RESULTS_DIR / f"semantic_benchmark_{timestamp}.json"
        latest = RESULTS_DIR / "latest_semantic_benchmark.json"
        payload = response.model_dump(mode="json")
        payload["output_path"] = str(timestamped)
        payload["latest_path"] = str(latest)
        for path in [timestamped, latest]:
            with path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        return timestamped, latest

    async def run(
        self,
        tenant_id: Optional[str] = None,
        min_pass_rate: float = 95.0,
        cases_path: Path = DEFAULT_CASES_PATH,
        case_ids: Optional[list[str]] = None,
        limit: Optional[int] = None,
        save: bool = True,
    ) -> SemanticBenchmarkResponse:
        tenant = tenant_id or self.settings.tenant_id
        selected_cases = self._select_cases(cases_path, case_ids=case_ids, limit=limit)
        outcomes = await run_regression_suite(selected_cases)
        summary = self.summarize(outcomes, min_pass_rate=min_pass_rate)
        response = SemanticBenchmarkResponse(
            status=summary.gate_status,
            tenant_id=tenant,
            source_fingerprint=self._source_fingerprint(tenant),
            summary=summary,
            results=[self._case_result(outcome) for outcome in outcomes],
        )
        if save:
            output_path, latest_path = self.save_response(response)
            response.output_path = str(output_path)
            response.latest_path = str(latest_path)
        return response

    def run_sync(
        self,
        tenant_id: Optional[str] = None,
        min_pass_rate: float = 95.0,
        cases_path: Path = DEFAULT_CASES_PATH,
        case_ids: Optional[list[str]] = None,
        limit: Optional[int] = None,
        save: bool = True,
    ) -> SemanticBenchmarkResponse:
        return asyncio.run(
            self.run(
                tenant_id=tenant_id,
                min_pass_rate=min_pass_rate,
                cases_path=cases_path,
                case_ids=case_ids,
                limit=limit,
                save=save,
            )
        )


semantic_benchmark_service = SemanticBenchmarkService()
