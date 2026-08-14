import json

from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.semantic.smoke_test_service import SemanticSmokeTestService


def _snapshot() -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="demo",
        database_name="demo_db",
        generated_at="2026-07-26T10:00:00",
        fingerprint="abc",
        tables=[
            DiscoveredTableInfo(
                name="training_requests",
                row_count=10,
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(
                        name="requester_role",
                        data_type="character varying",
                        udt_name="varchar",
                        sample_values=[ColumnSampleValue(value="کارمند اداری", count=3)],
                    ),
                    DiscoveredColumnInfo(name="estimated_cost", data_type="numeric", udt_name="numeric"),
                    DiscoveredColumnInfo(name="created_at", data_type="timestamp without time zone", udt_name="timestamp"),
                ],
                primary_keys=["id"],
            )
        ],
    )


def test_semantic_smoke_test_generation_creates_core_cases(monkeypatch):
    service = SemanticSmokeTestService()
    monkeypatch.setattr(
        "backend.semantic.smoke_test_service.database_onboarding_service.load_snapshot",
        lambda tenant_id=None: _snapshot(),
    )

    response = service.generate("demo")
    by_kind = {case.kind: case for case in response.cases}

    assert response.status == "success"
    assert response.source_fingerprint == "abc"
    assert {"count", "list", "sample_filter", "group_by", "max"}.issubset(by_kind)
    assert by_kind["count"].expected["aggregation"] == "COUNT"
    assert by_kind["sample_filter"].expected["filters"] == {"requester_role": "کارمند اداری"}
    assert "کارمند اداری" in by_kind["sample_filter"].question


def test_semantic_smoke_test_generation_blocks_without_discovery(monkeypatch):
    service = SemanticSmokeTestService()
    monkeypatch.setattr(
        "backend.semantic.smoke_test_service.database_onboarding_service.load_snapshot",
        lambda tenant_id=None: None,
    )

    response = service.generate("demo")

    assert response.status == "blocked"
    assert response.cases == []


def test_semantic_smoke_test_sync_writes_json(monkeypatch, tmp_path):
    service = SemanticSmokeTestService()
    monkeypatch.setattr(
        "backend.semantic.smoke_test_service.database_onboarding_service.load_snapshot",
        lambda tenant_id=None: _snapshot(),
    )
    output_path = tmp_path / "smoke_cases.json"

    response = service.sync("demo", output_path=output_path)

    assert response.status == "success"
    assert response.output_path == str(output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload[0]["id"].startswith("smoke_training_requests_")


def test_semantic_smoke_test_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main.semantic_smoke_test_service, "generate", lambda tenant_id=None, max_cases_per_table=5: SemanticSmokeTestService().generate("demo"))
    monkeypatch.setattr(
        "backend.semantic.smoke_test_service.database_onboarding_service.load_snapshot",
        lambda tenant_id=None: _snapshot(),
    )

    response = TestClient(app).get("/semantic/smoke-tests")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
