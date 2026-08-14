import pytest

from backend.database.models import SchemaDiscoveryResponse
from backend.semantic.lifecycle_service import semantic_lifecycle_service
from backend.semantic.models import (
    SemanticActivationResponse,
    SemanticBenchmarkResponse,
    SemanticBenchmarkSummary,
    SemanticFreshnessResponse,
    SemanticLifecycleResponse,
    SemanticLifecycleStep,
)


@pytest.mark.asyncio
async def test_semantic_auto_update_skips_when_fresh(monkeypatch):
    freshness = SemanticFreshnessResponse(
        status="up_to_date",
        tenant_id="education_ministry",
        message="fresh",
    )
    monkeypatch.setattr(semantic_lifecycle_service, "check_freshness", lambda **kwargs: freshness)

    result = await semantic_lifecycle_service.ensure_updated("education_ministry")

    assert result.status == "skipped"
    assert result.action == "none"
    assert result.lifecycle is None


@pytest.mark.asyncio
async def test_semantic_auto_update_runs_lifecycle_when_stale(monkeypatch):
    calls = {"freshness": 0, "run": 0}

    def fake_freshness(**kwargs):
        calls["freshness"] += 1
        if calls["freshness"] == 1:
            return SemanticFreshnessResponse(status="stale", tenant_id="education_ministry")
        return SemanticFreshnessResponse(status="up_to_date", tenant_id="education_ministry")

    async def fake_run(**kwargs):
        calls["run"] += 1
        return SemanticLifecycleResponse(
            status="ready",
            tenant_id="education_ministry",
            source_fingerprint="fp-new",
            steps=[SemanticLifecycleStep(name="semantic_benchmark", status="passed")],
            discovery=SchemaDiscoveryResponse(
                tenant_id="education_ministry",
                tables_discovered=7,
                relationships_found=7,
                fingerprint="fp-new",
                output_path="discovery.json",
                status="success",
            ),
            activation=SemanticActivationResponse(
                status="activated",
                tenant_id="education_ministry",
                source_fingerprint="fp-new",
            ),
            benchmark=SemanticBenchmarkResponse(
                status="passed",
                tenant_id="education_ministry",
                source_fingerprint="fp-new",
                summary=SemanticBenchmarkSummary(total=1, passed=1, pass_rate=100, gate_status="passed"),
            ),
        )

    monkeypatch.setattr(semantic_lifecycle_service, "check_freshness", fake_freshness)
    monkeypatch.setattr(semantic_lifecycle_service, "run", fake_run)

    result = await semantic_lifecycle_service.ensure_updated("education_ministry")

    assert result.status == "updated"
    assert result.action == "lifecycle_run"
    assert result.lifecycle.status == "ready"
    assert result.freshness_after.status == "up_to_date"
    assert calls == {"freshness": 2, "run": 1}
