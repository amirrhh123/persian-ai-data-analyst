from backend.database.models import ColumnSampleValue, DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot
from backend.semantic.models import (
    SemanticCatalog,
    SemanticColumn,
    SemanticColumnSuggestion,
    SemanticSuggestionSet,
    SemanticTable,
    SemanticTableSuggestion,
)
from backend.semantic.suggestion_service import semantic_suggestion_service


def test_semantic_suggestions_generate_core_entities():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    tables = {table.name: table for table in suggestions.tables}

    assert suggestions.status == "draft"
    assert suggestions.source_fingerprint
    assert tables["employees"].display_name_fa == "کارمندان"
    assert tables["students"].display_name_fa == "دانش‌آموزان"
    assert tables["schools"].display_name_fa == "مدارس"


def test_semantic_suggestions_map_pension_amount_to_senavat():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    terms = {term.term_fa: term for term in suggestions.business_terms}

    assert terms["سنوات"].maps_to == "retirement_records.pension_amount"
    assert terms["سابقه خدمت"].maps_to == "retirement_records.years_of_service"


def test_semantic_suggestions_include_student_province_path_rule():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    rules = {rule.name: rule for rule in suggestions.rules}

    assert rules["student_province_join_path"].applies_to == [
        "students",
        "schools",
        "organization_units",
    ]


def test_semantic_suggestions_mark_national_id_as_text_pii():
    suggestions = semantic_suggestion_service.generate("education_ministry")
    employees = next(table for table in suggestions.tables if table.name == "employees")
    national_id = next(column for column in employees.columns if column.name == "national_id")

    assert national_id.value_type == "text_identifier"
    assert national_id.pii is True
    assert "کد ملی" in national_id.aliases_fa


def test_semantic_suggestions_preserve_existing_human_aliases():
    suggestions = SemanticSuggestionSet(
        tenant_id="demo",
        source_fingerprint="abc",
        generated_at="2026-07-31T10:00:00",
        tables=[
            SemanticTableSuggestion(
                name="test",
                entity="test",
                display_name_fa="test",
                description_fa="unknown",
                aliases_fa=["test"],
                columns=[
                    SemanticColumnSuggestion(
                        name="requester_role",
                        data_type="text",
                        display_name_fa="requester_role",
                        description_fa="unknown",
                        aliases_fa=["requester_role"],
                    )
                ],
            )
        ],
    )
    existing = SemanticCatalog(
        tables=[
            SemanticTable(
                name="test",
                entity="test",
                description="جدول تست",
                aliases=["جدول تست"],
                columns=[
                    SemanticColumn(
                        name="requester_role",
                        data_type="text",
                        description="پست درخواست‌دهنده",
                        aliases=["پست"],
                        value_type="category",
                    )
                ],
            )
        ]
    )

    merged = semantic_suggestion_service._merge_existing_reviews(suggestions, existing)

    table = merged.tables[0]
    column = table.columns[0]
    assert table.aliases_fa == ["test", "جدول تست"]
    assert column.aliases_fa == ["requester_role", "پست"]
    assert column.value_type == "category"


def test_unknown_column_uses_database_comment_as_semantic_alias():
    column = DiscoveredColumnInfo(
        name="role_code", data_type="text", udt_name="text", comment="پست سازمانی"
    )
    suggestion = semantic_suggestion_service._suggest_column(column)
    assert suggestion.display_name_fa == "پست سازمانی"
    assert "پست سازمانی" in suggestion.aliases_fa


def test_categorical_sample_values_become_query_aliases():
    column = DiscoveredColumnInfo(
        name="requester_role", data_type="text", udt_name="text",
        sample_values=[ColumnSampleValue(value="کارمند اداری", count=4)],
    )
    suggestion = semantic_suggestion_service._suggest_column(column)
    assert "کارمند اداری" in suggestion.aliases_fa


def test_categorical_values_create_explicit_value_mappings():
    snapshot = SchemaDiscoverySnapshot(
        tenant_id="demo", database_name="demo", generated_at="now", fingerprint="fp",
        tables=[DiscoveredTableInfo(name="requests", columns=[DiscoveredColumnInfo(
            name="requester_role", data_type="text", udt_name="text",
            sample_values=[ColumnSampleValue(value="کارمند اداری", count=2)]
        )])], relationships=[]
    )
    suggestions = semantic_suggestion_service.generate("demo", discovery=snapshot)
    assert any(mapping.column == "requests.requester_role" and mapping.value == "کارمند اداری" for mapping in suggestions.value_mappings)
