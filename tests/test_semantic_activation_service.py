from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.suggestion_service import semantic_suggestion_service


def test_semantic_activation_validates_current_suggestions():
    result = semantic_activation_service.validate_current("education_ministry")

    assert result.status == "valid"
    assert result.issues == []
    assert result.tables >= 7
    assert result.joins >= 7


def test_semantic_activation_detects_fingerprint_mismatch():
    discovery = semantic_activation_service.load_discovery("education_ministry")
    suggestions = semantic_suggestion_service.generate("education_ministry")
    changed = suggestions.model_copy(update={"source_fingerprint": "not-current"})

    issues = semantic_activation_service.validate(changed, discovery)

    assert any(issue.code == "fingerprint_mismatch" for issue in issues)


def test_semantic_activation_builds_active_catalog_with_business_terms():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    catalog = semantic_activation_service.build_active_catalog(suggestions)

    assert catalog.table("employees").column("national_id").pii is True
    assert any(
        rule.name == "business_term_retirement_records_pension_amount"
        and "retirement_records.pension_amount" in rule.applies_to
        for rule in catalog.rules
    )


def test_semantic_activation_writes_active_catalog():
    result = semantic_activation_service.activate("education_ministry")

    assert result.status == "activated"
    assert result.active_catalog_path
    active = semantic_activation_service.load_active_catalog("education_ministry")
    assert active.table("students").entity == "student"
