from backend.semantic.suggestion_service import semantic_suggestion_service


def test_semantic_suggestions_include_confidence_reasons():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    employees = next(table for table in suggestions.tables if table.name == "employees")
    national_id = next(column for column in employees.columns if column.name == "national_id")

    assert employees.confidence >= 0.85
    assert "known_table_mapping" in employees.confidence_reasons
    assert "primary_key_available" in employees.confidence_reasons
    assert national_id.confidence >= 0.85
    assert "known_column_mapping" in national_id.confidence_reasons
    assert "pii_requires_policy" in national_id.confidence_reasons


def test_semantic_suggestions_require_review_for_low_confidence_table(tmp_path):
    from backend.database.models import DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot
    from backend.semantic.suggestion_service import SemanticSuggestionService

    service = SemanticSuggestionService()
    service.schema_root = tmp_path
    tenant_dir = tmp_path / "demo"
    tenant_dir.mkdir()
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="demo",
        database_name="demo_db",
        generated_at="2026-07-26T10:00:00",
        fingerprint="abc",
        tables=[
            DiscoveredTableInfo(
                name="mystery_records",
                row_count=10,
                columns=[
                    DiscoveredColumnInfo(name="opaque_text", data_type="character varying", udt_name="varchar"),
                    DiscoveredColumnInfo(name="amount", data_type="numeric", udt_name="numeric"),
                ],
            )
        ],
    )
    (tenant_dir / "discovery.json").write_text(snapshot.model_dump_json(), encoding="utf-8")

    suggestions = service.generate("demo")
    table = suggestions.tables[0]

    assert table.confidence < 0.85
    assert table.review_required is True
    assert "heuristic_table_mapping" in table.confidence_reasons
    assert "missing_primary_key" in table.confidence_reasons
    assert any(column.confidence < 0.55 for column in table.columns)
