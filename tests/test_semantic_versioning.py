import json

from backend.semantic.activation_service import semantic_activation_service


def test_semantic_activation_creates_version_backup():
    result = semantic_activation_service.activate("education_ministry")

    assert result.status == "activated"
    assert result.backup_path
    assert result.active_catalog_path

    versions = semantic_activation_service.list_versions("education_ministry")
    assert any(version.path == result.backup_path for version in versions)


def test_semantic_rollback_restores_selected_version():
    activation = semantic_activation_service.activate("education_ministry")
    versions = semantic_activation_service.list_versions("education_ministry")
    version_id = next(version.version_id for version in versions if version.path == activation.backup_path)

    rollback = semantic_activation_service.rollback(version_id, "education_ministry")

    assert rollback.status == "rolled_back"
    assert rollback.restored_version_id == version_id
    with open(rollback.active_catalog_path, "r", encoding="utf-8") as file:
        restored = json.load(file)
    assert restored["tables"]
    assert restored["rules"]


def test_semantic_rollback_reports_missing_version():
    result = semantic_activation_service.rollback("missing-version", "education_ministry")

    assert result.status == "not_found"
