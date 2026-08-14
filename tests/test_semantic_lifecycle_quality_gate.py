import pytest

from backend.database.models import SchemaDiscoveryResponse
from backend.semantic.lifecycle_service import SemanticLifecycleService


@pytest.mark.asyncio
async def test_semantic_lifecycle_stops_when_schema_quality_gate_blocks(monkeypatch):
    service = SemanticLifecycleService()

    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.schema_discovery_service.sync_discovery",
        lambda **kwargs: SchemaDiscoveryResponse(
            tenant_id="demo",
            tables_discovered=0,
            relationships_found=0,
            fingerprint="abc",
            output_path="schema/tenants/demo/discovery.json",
            status="success",
        ),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.database_onboarding_service.load_snapshot",
        lambda tenant_id=None: None,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("semantic suggestions should not run when quality gate is blocked")

    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_suggestion_service.sync",
        fail_if_called,
    )

    response = await service.run(tenant_id="demo")

    assert response.status == "blocked"
    assert [step.name for step in response.steps] == ["schema_discovery", "schema_quality_gate"]
    assert response.steps[-1].status == "blocked"
