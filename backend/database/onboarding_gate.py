"""Hard onboarding readiness gate (accuracy work #5).

One command decides whether a freshly connected database is allowed to serve
user questions. It composes the existing lifecycle pieces in the SAFE order —
benchmark BEFORE activation, never after:

    discover → schema sync → suggestions → alias enrichment → value index
    → [auto_fix: lightweight gaps] → smoke cases → benchmark
    → activate ONLY if pass_rate >= threshold

The verdict and full step report are persisted to
``schema/tenants/{tenant}/onboarding_gate.json`` so deployment records are
auditable. Activation still keeps its own validation; this gate adds the
quality contract on top.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.config import get_settings


VERDICT_READY = "ready"
VERDICT_BLOCKED = "blocked"
VERDICT_FAILED = "failed"


class GateStep(BaseModel):
    name: str
    status: str
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: float = 0.0


class OnboardingGateReport(BaseModel):
    tenant_id: str
    verdict: str
    min_pass_rate: float
    pass_rate: float = 0.0
    steps: List[GateStep] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    generated_at: str = ""

    def dict_for_file(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class OnboardingGateService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.schema_root = Path(__file__).parent.parent.parent / "schema" / "tenants"

    # ------------------------------------------------------------------

    def report_path(self, tenant_id: str) -> Path:
        return self.schema_root / tenant_id / "onboarding_gate.json"

    def load_last_report(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        path = self.report_path(tenant_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self, tenant_id: str, report: OnboardingGateReport) -> Path:
        path = self.report_path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.dict_for_file(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _step(name: str, status: str, message: str, started: float, **details) -> GateStep:
        return GateStep(
            name=name,
            status=status,
            message=message,
            details=details,
            elapsed_ms=round((time.time() - started) * 1000, 2),
        )

    # ------------------------------------------------------------------

    async def run(
        self,
        tenant_id: Optional[str] = None,
        *,
        auto_fix: Optional[bool] = None,
        benchmark_limit: Optional[int] = None,
        max_prompts: int = 40,
    ) -> OnboardingGateReport:
        from backend.database.discovery_service import schema_discovery_service
        from backend.database.sync_service import schema_sync_service
        from backend.feedback.service import feedback_service  # noqa: F401 (loop ready)
        from backend.semantic.activation_service import semantic_activation_service
        from backend.semantic.alias_enrichment import alias_enrichment_service
        from backend.semantic.benchmark_service import semantic_benchmark_service
        from backend.semantic.lightweight_gap_service import lightweight_gap_service
        from backend.semantic.suggestion_service import semantic_suggestion_service
        from backend.semantic.smoke_test_service import semantic_smoke_test_service
        from backend.value_index.service import value_index_service

        tenant = tenant_id or self.settings.tenant_id
        threshold = float(self.settings.onboarding_gate_min_pass_rate)
        do_auto_fix = self.settings.onboarding_gate_auto_fix if auto_fix is None else auto_fix

        steps: List[GateStep] = []
        blockers: List[str] = []

        def finish(verdict: str, pass_rate: float = 0.0, actions: Optional[List[str]] = None) -> OnboardingGateReport:
            report = OnboardingGateReport(
                tenant_id=tenant,
                verdict=verdict,
                min_pass_rate=threshold,
                pass_rate=pass_rate,
                steps=steps,
                blockers=list(blockers),
                next_actions=actions or [],
                generated_at=datetime.now().isoformat(timespec="seconds"),
            )
            self._save(tenant, report)
            return report

        # 1. Discovery ---------------------------------------------------
        started = time.time()
        discovery = schema_discovery_service.sync_discovery(tenant_id=tenant)
        if discovery.status != "success":
            steps.append(self._step("discovery", "error", discovery.status, started))
            blockers.append(f"Discovery failed: {discovery.status}")
            return finish(VERDICT_FAILED)
        steps.append(self._step(
            "discovery", "success",
            f"Discovered {discovery.tables_discovered} tables "
            f"({discovery.inferred_relationships} inferred joins).",
            started,
            tables=discovery.tables_discovered,
            relationships=discovery.relationships_found,
        ))

        # 2. Validator schema cache --------------------------------------
        started = time.time()
        synced = schema_sync_service.sync_schema(tenant)
        if synced.status != "success":
            blockers.append(f"Schema cache sync failed: {synced.status}")
            steps.append(self._step("schema_cache", "error", synced.status, started))
            return finish(VERDICT_FAILED)
        steps.append(self._step("schema_cache", "success", "Validator schema cache updated.", started))

        # 3. Suggestions + alias enrichment ------------------------------
        started = time.time()
        suggestions, _sugg_path = semantic_suggestion_service.sync(tenant_id=tenant)
        suggestions, enrich_stats = await alias_enrichment_service.enrich_suggestions(
            tenant, suggestions, max_prompts=max_prompts
        )
        semantic_suggestion_service.save(suggestions)
        steps.append(self._step(
            "alias_enrichment",
            "success" if enrich_stats.get("enabled") else "warning",
            (
                f"{enrich_stats.get('aliases_added', 0)} aliases across "
                f"{enrich_stats.get('columns_enriched', 0)} columns"
                if enrich_stats.get("enabled")
                else f"skipped: {enrich_stats.get('reason')}"
            ),
            started,
        ))

        # 4. Value index -------------------------------------------------
        started = time.time()
        pii_columns: set[str] = set()
        column_aliases: Dict[str, List[str]] = {}
        for table in suggestions.tables:
            for column in table.columns:
                key = f"{table.name}.{column.name}"
                column_aliases[key] = [column.name, column.display_name_fa, *column.aliases_fa]
                if column.pii:
                    pii_columns.add(key)

        from backend.database.onboarding_service import database_onboarding_service

        snapshot = database_onboarding_service.load_snapshot(tenant)
        if snapshot is None:
            blockers.append("Discovery snapshot unavailable for value index")
            steps.append(self._step("value_index", "error", "no snapshot", started))
            return finish(VERDICT_FAILED)
        value_index, _path = value_index_service.sync(
            snapshot, column_aliases=column_aliases, pii_columns=pii_columns
        )
        if self.settings.value_index_deep_enabled:
            try:
                value_index, _deep = value_index_service.deep_refresh(value_index, snapshot)
                value_index_service.save(value_index)
            except Exception:
                pass
        steps.append(self._step(
            "value_index", "success",
            f"{len(value_index.entries)} indexed values.",
            started,
        ))

        # 5. Optional auto-fix of safe lightweight gaps ------------------
        if do_auto_fix:
            started = time.time()
            try:
                gap_response = await lightweight_gap_service.suggest(tenant, limit=None)
                gap_count = len(gap_response.suggestions or [])
                applied = {}
                if gap_count:
                    applied = await lightweight_gap_service.apply_suggestions(
                        tenant, limit=None, validate_after=False
                    )
                steps.append(self._step(
                    "auto_fix_gaps", "success",
                    f"{gap_count} gaps found; applied={applied.get('applied', 0)}.",
                    started,
                ))
            except Exception as exc:
                steps.append(self._step("auto_fix_gaps", "warning", str(exc)[:120], started))

        # 6. Smoke cases -------------------------------------------------
        started = time.time()
        smoke = semantic_smoke_test_service.sync(tenant_id=tenant)
        if smoke.status != "success":
            blockers.append(f"Smoke case generation failed: {smoke.status}")
            steps.append(self._step("smoke_cases", "error", smoke.status, started))
            return finish(VERDICT_BLOCKED, actions=["Fix schema issues blocking smoke case generation."])
        steps.append(self._step(
            "smoke_cases", "success", f"{len(smoke.cases)} cases generated.", started
        ))

        # 7. Benchmark (BEFORE activation) --------------------------------
        started = time.time()
        benchmark = await semantic_benchmark_service.run(
            tenant_id=tenant,
            min_pass_rate=threshold,
            limit=benchmark_limit,
        )
        pass_rate = float(benchmark.summary.pass_rate or 0.0)
        steps.append(self._step(
            "benchmark",
            "passed" if pass_rate >= threshold else "failed",
            f"{benchmark.summary.passed}/{benchmark.summary.total} passed ({pass_rate}%).",
            started,
            total=benchmark.summary.total,
        ))
        if pass_rate < threshold:
            blockers.append(
                f"Benchmark pass rate {pass_rate}% is below the required {threshold}%."
            )
            return finish(
                VERDICT_BLOCKED,
                pass_rate,
                [
                    "Review failing cases via «پیشنهاد رفع نواقص حالت سبک» then re-run this gate.",
                    "Or run /semantic/review with human-approved corrections, then re-run.",
                ],
            )

        # 8. Activation (gated) ------------------------------------------
        started = time.time()
        activation = semantic_activation_service.activate(tenant, force=False)
        activated = activation.status.startswith("activated")
        steps.append(self._step(
            "activation",
            "success" if activated else "error",
            activation.status,
            started,
        ))
        if not activated:
            blockers.append(f"Activation refused: {activation.status}")
            return finish(
                VERDICT_BLOCKED,
                pass_rate,
                ["Run /semantic/review to resolve flagged items, then re-run the gate."],
            )

        return finish(
            VERDICT_READY,
            pass_rate,
            ["System is ready to answer questions for this tenant."],
        )


onboarding_gate_service = OnboardingGateService()
