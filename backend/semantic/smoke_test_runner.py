import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline
from backend.semantic.models import (
    SemanticSmokeTestCase,
    SemanticSmokeTestResult,
    SemanticSmokeTestRunResponse,
    SemanticSmokeTestRunSummary,
)
from backend.semantic.smoke_test_service import DEFAULT_OUTPUT_PATH, semantic_smoke_test_service


RESULTS_DIR = Path(__file__).parent.parent.parent / "tests" / "results"


class SemanticSmokeTestRunner:
    def __init__(self):
        self.settings = get_settings()

    def load_cases(self, cases_path: Path = DEFAULT_OUTPUT_PATH) -> list[SemanticSmokeTestCase]:
        payload = json.loads(cases_path.read_text(encoding="utf-8"))
        return [SemanticSmokeTestCase.model_validate(item) for item in payload]

    async def run(
        self,
        tenant_id: Optional[str] = None,
        cases_path: Path = DEFAULT_OUTPUT_PATH,
        limit: Optional[int] = None,
        execute: bool = False,
        save: bool = True,
        generate_if_missing: bool = True,
    ) -> SemanticSmokeTestRunResponse:
        tenant = tenant_id or self.settings.tenant_id
        if not cases_path.exists() and generate_if_missing:
            semantic_smoke_test_service.sync(tenant_id=tenant, output_path=cases_path)
        cases = self.load_cases(cases_path)
        if limit is not None:
            cases = cases[:limit]

        results = [await self._run_case(case, execute=execute) for case in cases]
        summary = self._summarize(results)
        response = SemanticSmokeTestRunResponse(
            status="passed" if summary.failed == 0 else "failed",
            tenant_id=tenant,
            source_fingerprint=self._source_fingerprint(cases),
            summary=summary,
            results=results,
        )
        if save:
            output_path, latest_path = self.save_response(response)
            response.output_path = str(output_path)
            response.latest_path = str(latest_path)
        return response

    async def _run_case(self, case: SemanticSmokeTestCase, execute: bool = False) -> SemanticSmokeTestResult:
        start = time.time()
        response = await query_pipeline.execute(PipelineRequest(question=case.question, execute=execute))
        elapsed_ms = (time.time() - start) * 1000
        response_dict = response.model_dump(mode="json")
        failures = self._evaluate(case, response_dict)
        return SemanticSmokeTestResult(
            id=case.id,
            table=case.table,
            kind=case.kind,
            question=case.question,
            passed=not failures,
            failures=failures,
            error_code=self._error_code(response_dict, failures),
            failure_stage=self._failure_stage(response_dict, failures),
            elapsed_ms=round(elapsed_ms, 2),
            sql=response_dict.get("sql") or "",
            response=response_dict,
        )

    def _evaluate(self, case: SemanticSmokeTestCase, response: dict) -> list[str]:
        failures = []
        expected = case.expected
        sql = response.get("sql") or ""

        if response.get("rejected"):
            failures.append(f"query rejected: {response.get('rejection_reason')}")
        if response.get("unsupported"):
            failures.append(f"query unsupported: {response.get('unsupported_reason')}")
        if response.get("needs_clarification"):
            failures.append(f"query needs clarification: {response.get('clarification_question')}")
        if response.get("valid") is False:
            failures.append("pipeline response is not valid")

        for snippet in expected.get("sql_contains", []):
            if str(snippet) not in sql:
                failures.append(f"sql missing snippet: {snippet}")

        intent = response.get("intent") or {}
        if expected.get("aggregation") and intent.get("aggregation") != expected["aggregation"]:
            failures.append(f"aggregation: expected {expected['aggregation']!r}, got {intent.get('aggregation')!r}")
        if expected.get("wants_list") and not intent.get("wants_list"):
            failures.append("intent.wants_list is false")

        return failures

    def _failure_stage(self, response: dict, failures: list[str]) -> str:
        if not failures:
            return ""
        if response.get("rejected"):
            return "safety"
        if response.get("unsupported"):
            return "unsupported"
        if response.get("needs_clarification"):
            return "ambiguity"
        if response.get("valid") is False:
            return "validation"
        if not response.get("sql"):
            return "routing"
        return "expectation"

    def _error_code(self, response: dict, failures: list[str]) -> str:
        if not failures:
            return ""
        details = response.get("error_details") or []
        if details:
            return details[0].get("code", "")
        if response.get("rejected"):
            return "safety.rejected"
        if response.get("unsupported"):
            return "unsupported.out_of_scope"
        if response.get("needs_clarification"):
            return "ambiguity.clarification_required"
        if response.get("valid") is False:
            return "sql.validation_failed"
        if not response.get("sql"):
            return "routing.no_sql"
        return "expectation.mismatch"

    def _summarize(self, results: list[SemanticSmokeTestResult]) -> SemanticSmokeTestRunSummary:
        total = len(results)
        passed = sum(1 for result in results if result.passed)
        avg_elapsed = round(sum(result.elapsed_ms for result in results) / total, 2) if total else 0.0
        deterministic_sql = sum(
            1
            for result in results
            if (result.response.get("generation_source") in {"template", "semantic", "rules"})
        )
        llm_sql = sum(1 for result in results if result.response.get("generation_source") == "llm")
        llm_required = sum(
            1
            for result in results
            if (
                result.response.get("generation_source") == "llm_disabled"
                or result.error_code == "sql.llm_disabled"
            )
        )
        lightweight_ready = sum(
            1
            for result in results
            if result.passed and result.response.get("generation_source") in {"template", "semantic", "rules"}
        )
        return SemanticSmokeTestRunSummary(
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=round((passed / total * 100), 2) if total else 0.0,
            avg_elapsed_ms=avg_elapsed,
            deterministic_sql=deterministic_sql,
            llm_sql=llm_sql,
            llm_required=llm_required,
            lightweight_ready=lightweight_ready,
            lightweight_ready_rate=round((lightweight_ready / total * 100), 2) if total else 0.0,
        )

    def save_response(self, response: SemanticSmokeTestRunResponse) -> tuple[Path, Path]:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped = RESULTS_DIR / f"semantic_smoke_test_{timestamp}.json"
        latest = RESULTS_DIR / "latest_semantic_smoke_test.json"
        payload = response.model_dump(mode="json")
        payload["output_path"] = str(timestamped)
        payload["latest_path"] = str(latest)
        for path in [timestamped, latest]:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return timestamped, latest

    def _source_fingerprint(self, cases: list[SemanticSmokeTestCase]) -> str:
        return ""


semantic_smoke_test_runner = SemanticSmokeTestRunner()
