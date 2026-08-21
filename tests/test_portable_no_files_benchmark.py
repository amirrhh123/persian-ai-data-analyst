from pathlib import Path

from backend.database.models import DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot
from backend.knowledge.loader import KnowledgeLoader
from backend.reports.group_loader import GroupLoader
from backend.semantic.runtime_bootstrap import RuntimeSemanticBootstrap
from backend.pipeline.intent import extract_intent


def test_portable_mode_without_knowledge_or_schema_files(tmp_path: Path, monkeypatch):
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="portable", database_name="demo", generated_at="now", fingerprint="portable",
        tables=[DiscoveredTableInfo(
            name="people", row_count=3,
            columns=[
                DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                DiscoveredColumnInfo(name="full_name", data_type="text", udt_name="text"),
            ], primary_keys=["id"]
        )], relationships=[]
    )
    runtime = RuntimeSemanticBootstrap()
    runtime.root = tmp_path / ".runtime"
    monkeypatch.setattr("backend.semantic.runtime_bootstrap.schema_discovery_service.discover", lambda **_: snapshot)
    monkeypatch.setattr("backend.semantic.loader.runtime_semantic_bootstrap", runtime, raising=False)

    # Both directories intentionally do not exist.
    knowledge = KnowledgeLoader(tmp_path / "knowledge" / "tenants" / "portable")
    groups = GroupLoader(tmp_path / "knowledge" / "tenants" / "portable")
    catalog = runtime.load("portable", discovery=snapshot)
    monkeypatch.setattr("backend.semantic.loader.load_tenant_semantic_catalog", lambda tenant=None: catalog)

    reports = knowledge.load_all_reports()
    generated_groups = groups.load_all_groups()
    assert reports and reports[0].linked_table == "people"
    assert generated_groups and generated_groups[0].linked_tables == ["people"]


def test_portable_routing_baseline_cases_without_knowledge_or_schema(tmp_path: Path, monkeypatch):
    # The runtime catalog is the only semantic source in this benchmark.
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="portable", database_name="demo", generated_at="now", fingerprint="routing",
        tables=[
            DiscoveredTableInfo(name="students", columns=[DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4")]),
            DiscoveredTableInfo(name="employees", columns=[DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4")]),
        ], relationships=[]
    )
    runtime = RuntimeSemanticBootstrap(); runtime.root = tmp_path / ".runtime"
    catalog = runtime.load("portable", discovery=snapshot)
    monkeypatch.setattr("backend.semantic.loader.load_tenant_semantic_catalog", lambda tenant=None: catalog)
    assert extract_intent("اطلاعات دانش آموزان").requested_entity == "student"
    assert extract_intent("اطلاعات کارمندان").requested_entity == "employee"
