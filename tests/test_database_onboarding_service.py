from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    ForeignKeyInfo,
    IndexInfo,
    RelationshipInfo,
    SchemaDiscoverySnapshot,
)
from backend.database.onboarding_service import DatabaseOnboardingService


def _snapshot() -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="demo",
        database_name="demo_db",
        schema_name="public",
        generated_at="2026-07-26T10:00:00",
        fingerprint="abc",
        tables=[
            DiscoveredTableInfo(
                name="employees",
                row_count=10,
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(
                        name="national_id",
                        data_type="character varying",
                        udt_name="varchar",
                        sample_values=[ColumnSampleValue(value="8223876400", count=1)],
                    ),
                    DiscoveredColumnInfo(
                        name="position",
                        data_type="character varying",
                        udt_name="varchar",
                        sample_values=[ColumnSampleValue(value="کارمند اداری", count=3)],
                    ),
                    DiscoveredColumnInfo(name="organization_unit_id", data_type="integer", udt_name="int4"),
                ],
                primary_keys=["id"],
                foreign_keys=[
                    ForeignKeyInfo(
                        table_name="employees",
                        column_name="organization_unit_id",
                        foreign_table_name="organization_units",
                        foreign_column_name="id",
                    )
                ],
                indexes=[IndexInfo(name="employees_pkey", definition="CREATE UNIQUE INDEX employees_pkey")],
            ),
            DiscoveredTableInfo(
                name="organization_units",
                row_count=2,
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(
                        name="province",
                        data_type="character varying",
                        udt_name="varchar",
                        sample_values=[ColumnSampleValue(value="تهران", count=1)],
                    ),
                ],
                primary_keys=["id"],
                indexes=[IndexInfo(name="organization_units_pkey", definition="CREATE UNIQUE INDEX ou_pkey")],
            ),
        ],
        relationships=[
            RelationshipInfo(
                source_table="employees",
                source_column="organization_unit_id",
                target_table="organization_units",
                target_column="id",
            )
        ],
    )


def test_onboarding_report_blocks_when_discovery_is_missing():
    service = DatabaseOnboardingService()

    report = service.build_report(None)

    assert report["status"] == "blocked"
    assert report["summary"]["blockers"] == 1
    assert report["recommended_actions"]


def test_onboarding_report_summarizes_ready_schema_and_sensitive_columns():
    service = DatabaseOnboardingService()

    report = service.build_report(_snapshot())

    assert report["status"] == "ok"
    assert report["summary"]["tables"] == 2
    assert report["summary"]["relationships"] == 1
    assert report["summary"]["sensitive_columns"] == 1
    assert report["tables"][0]["sensitive_columns"][0]["column"] == "national_id"
    assert all(check["status"] == "ok" for check in report["checks"])


def test_onboarding_report_warns_for_missing_primary_key_relationships_and_samples():
    snapshot = _snapshot()
    snapshot.relationships = []
    snapshot.tables[0].primary_keys = []
    snapshot.tables[0].columns[2].sample_values = []

    service = DatabaseOnboardingService()
    report = service.build_report(snapshot)

    assert report["status"] == "warning"
    assert report["summary"]["warnings"] >= 3
    assert any(check["id"] == "relationships_present" for check in report["checks"])
    assert any(check["id"] == "primary_keys" for check in report["checks"])
    assert any(check["id"] == "sample_values" for check in report["checks"])


def test_onboarding_report_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main.database_onboarding_service, "load_snapshot", lambda tenant_id=None: _snapshot())

    response = TestClient(app).get("/database/onboarding-report")

    assert response.status_code == 200
    assert response.json()["summary"]["tables"] == 2


def test_schema_quality_gate_passes_ready_schema():
    service = DatabaseOnboardingService()

    gate = service.quality_gate(_snapshot())

    assert gate["status"] == "passed"
    assert gate["blockers"] == []
    assert gate["warnings"] == []


def test_schema_quality_gate_blocks_missing_discovery():
    service = DatabaseOnboardingService()

    gate = service.quality_gate(None)

    assert gate["status"] == "blocked"
    assert gate["blockers"]


def test_schema_quality_gate_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main.database_onboarding_service, "load_snapshot", lambda tenant_id=None: _snapshot())

    response = TestClient(app).get("/database/schema-quality-gate")

    assert response.status_code == 200
    assert response.json()["status"] == "passed"
