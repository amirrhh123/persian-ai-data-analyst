import pytest

from backend.database.models import SchemaDiscoveryResponse
from backend.semantic.lifecycle_service import semantic_lifecycle_service


@pytest.mark.asyncio
async def test_semantic_lifecycle_runs_end_to_end_with_small_benchmark():
    response = await semantic_lifecycle_service.run(
        tenant_id="education_ministry",
        min_pass_rate=0,
        benchmark_limit=1,
    )

    assert response.status == "ready"
    assert [step.name for step in response.steps] == [
        "schema_discovery",
        "validator_schema_sync",
        "schema_quality_gate",
        "semantic_suggestions",
        "value_index_sync",
        "semantic_activation",
        "semantic_benchmark",
    ]
    assert response.steps[1].status == "success"
    assert response.steps[2].status in {"passed", "passed_with_warnings"}
    assert response.discovery.tables_discovered >= 7
    assert response.activation.status in {"activated", "activated_with_warnings"}
    assert response.benchmark.summary.total == 1


@pytest.mark.asyncio
async def test_semantic_lifecycle_stops_when_discovery_fails(monkeypatch):
    def fake_sync_discovery(**kwargs):
        return SchemaDiscoveryResponse(
            tenant_id=kwargs["tenant_id"],
            tables_discovered=0,
            relationships_found=0,
            fingerprint="",
            output_path=None,
            status="error: unavailable",
        )

    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.schema_discovery_service.sync_discovery",
        fake_sync_discovery,
    )

    response = await semantic_lifecycle_service.run(tenant_id="education_ministry")

    assert response.status == "failed"
    assert [step.name for step in response.steps] == ["schema_discovery"]
