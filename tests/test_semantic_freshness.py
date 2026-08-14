from backend.database.models import SchemaDiscoverySnapshot
from backend.semantic.lifecycle_service import semantic_lifecycle_service
from backend.semantic.models import SemanticSuggestionSet


def _snapshot(fingerprint: str = "fp-current") -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="education_ministry",
        database_name="test",
        schema_name="public",
        generated_at="2026-07-21T00:00:00",
        fingerprint=fingerprint,
        tables=[],
        relationships=[],
    )


def _suggestions(fingerprint: str = "fp-current") -> SemanticSuggestionSet:
    return SemanticSuggestionSet(
        tenant_id="education_ministry",
        source_fingerprint=fingerprint,
        generated_at="2026-07-21T00:00:00",
    )


def test_semantic_freshness_reports_up_to_date(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.schema_discovery_service.discover",
        lambda **kwargs: _snapshot("fp-current"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.load_discovery",
        lambda tenant_id: _snapshot("fp-current"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.load_suggestions",
        lambda tenant_id: _suggestions("fp-current"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.active_catalog_path",
        lambda tenant_id: tmp_path / "semantic_active.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.discovery_path",
        lambda tenant_id: tmp_path / "discovery.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: tmp_path / "semantic_suggestions.json",
    )
    for name in ["semantic_active.json", "discovery.json", "semantic_suggestions.json"]:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    result = semantic_lifecycle_service.check_freshness("education_ministry")

    assert result.status == "up_to_date"
    assert result.recommended_action == "No action is required."


def test_semantic_freshness_reports_stale_when_database_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.schema_discovery_service.discover",
        lambda **kwargs: _snapshot("fp-new"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.load_discovery",
        lambda tenant_id: _snapshot("fp-old"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.load_suggestions",
        lambda tenant_id: _suggestions("fp-old"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.active_catalog_path",
        lambda tenant_id: tmp_path / "semantic_active.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.discovery_path",
        lambda tenant_id: tmp_path / "discovery.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: tmp_path / "semantic_suggestions.json",
    )
    for name in ["semantic_active.json", "discovery.json", "semantic_suggestions.json"]:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    result = semantic_lifecycle_service.check_freshness("education_ministry")

    assert result.status == "stale"
    assert result.current_fingerprint == "fp-new"
    assert result.stored_fingerprint == "fp-old"


def test_semantic_freshness_reports_missing_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.schema_discovery_service.discover",
        lambda **kwargs: _snapshot("fp-current"),
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.active_catalog_path",
        lambda tenant_id: tmp_path / "semantic_active.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.discovery_path",
        lambda tenant_id: tmp_path / "discovery.json",
    )
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: tmp_path / "semantic_suggestions.json",
    )

    result = semantic_lifecycle_service.check_freshness("education_ministry")

    assert result.status == "missing_metadata"
    assert result.recommended_action.startswith("Run the full semantic lifecycle")
