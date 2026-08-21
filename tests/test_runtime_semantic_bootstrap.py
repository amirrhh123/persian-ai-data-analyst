from pathlib import Path

from backend.database.models import DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot
from backend.semantic.runtime_bootstrap import RuntimeSemanticBootstrap


def test_runtime_bootstrap_builds_catalog_without_schema_or_knowledge_files(tmp_path: Path, monkeypatch):
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="portable",
        database_name="demo",
        generated_at="2026-01-01T00:00:00",
        fingerprint="portable-fingerprint",
        tables=[DiscoveredTableInfo(
            name="people",
            row_count=2,
            primary_keys=["id"],
            columns=[
                DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                DiscoveredColumnInfo(name="full_name", data_type="text", udt_name="text"),
            ],
        )],
    )
    bootstrap = RuntimeSemanticBootstrap()
    bootstrap.root = tmp_path
    catalog = bootstrap.load("portable", discovery=snapshot)

    assert catalog.table("people") is not None
    assert catalog.table("people").column("full_name") is not None
    assert (tmp_path / "portable" / "portable-fingerprint.json").exists()


def test_runtime_bootstrap_uses_fresh_cache_without_discovery(tmp_path: Path, monkeypatch):
    bootstrap = RuntimeSemanticBootstrap()
    bootstrap.root = tmp_path
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="portable", database_name="demo", generated_at="2026-01-01T00:00:00",
        fingerprint="cached", tables=[DiscoveredTableInfo(name="people", columns=[])]
    )
    bootstrap.load("portable", discovery=snapshot)
    monkeypatch.setattr(
        "backend.semantic.runtime_bootstrap.schema_discovery_service.discover",
        lambda **_: (_ for _ in ()).throw(AssertionError("discovery should not run")),
    )
    assert bootstrap.load("portable").table("people") is not None


def test_runtime_refresh_rebuilds_only_for_new_fingerprint(tmp_path: Path, monkeypatch):
    bootstrap = RuntimeSemanticBootstrap()
    bootstrap.root = tmp_path
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="portable", database_name="demo", generated_at="2026-01-01T00:00:00",
        fingerprint="new-fingerprint", tables=[DiscoveredTableInfo(name="people", columns=[])]
    )
    monkeypatch.setattr(
        "backend.semantic.runtime_bootstrap.schema_discovery_service.discover",
        lambda **_: snapshot,
    )
    _, rebuilt, _ = bootstrap.refresh("portable")
    assert rebuilt is True
    _, rebuilt_again, _ = bootstrap.refresh("portable")
    assert rebuilt_again is False
