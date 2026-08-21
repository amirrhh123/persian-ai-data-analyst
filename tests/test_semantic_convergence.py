from __future__ import annotations

from backend.pipeline.intent import QueryIntent, extract_intent
from backend.semantic.compiler import semantic_compiler
from backend.semantic.context_index import semantic_context_index_service
from backend.semantic.models import (
    SemanticCatalog,
    SemanticColumn,
    SemanticMetric,
    SemanticTable,
    SemanticReviewRequest,
    SemanticSuggestionSet,
    SemanticTableSuggestion,
)
from backend.semantic.review_service import SemanticReviewService
from backend.semantic.resolver import SemanticResolver
from backend.semantic.snapshot import SemanticSnapshot
from backend.sql.models import SQLPlan
from backend.sql.templates import render_template_sql


def catalog() -> SemanticCatalog:
    return SemanticCatalog(
        version=12,
        tables=[
            SemanticTable(
                name="employees",
                entity="employee",
                description="کارمندان",
                aliases=["همکاران سازمان"],
                columns=[
                    SemanticColumn(
                        name="position",
                        data_type="text",
                        description="سمت سازمانی",
                        aliases=["پست سازمانی"],
                    ),
                    SemanticColumn(
                        name="status",
                        data_type="text",
                        description="وضعیت",
                        aliases=["وضعیت همکاری"],
                    ),
                ],
            )
        ],
        business_terms=[{
            "term_fa": "عنوان شغلی",
            "aliases_fa": ["سمت کاری"],
            "maps_to": "employees.position",
            "description_fa": "عنوان شغلی تأییدشده",
        }],
        value_mappings=[{
            "term_fa": "مشغول به کار",
            "aliases_fa": ["در حال همکاری"],
            "column": "employees.status",
            "value": "active",
            "description_fa": "کارمند فعال",
        }],
        metrics=[SemanticMetric(
            name="active_employee_count",
            table="employees",
            expression="employees.id",
            aggregation="COUNT_DISTINCT",
            aliases=["تعداد همکار فعال"],
        )],
    )


def snapshot() -> SemanticSnapshot:
    semantic_catalog = catalog()
    context_index = semantic_context_index_service.build("test", semantic_catalog)
    return SemanticSnapshot(
        tenant_id="test",
        catalog=semantic_catalog,
        compiled=semantic_compiler.compile(semantic_catalog),
        context_index=context_index,
        captured_at="2026-01-01T00:00:00+00:00",
    )


def test_extract_intent_uses_injected_snapshot_without_global_catalog() -> None:
    intent = extract_intent("پست سازمانی همکاران سازمان", catalog())

    assert intent.requested_entity == "employee"
    assert "position" in intent.requested_columns


def test_compiler_gives_human_business_terms_and_values_executable_rules() -> None:
    compiled = snapshot().compiled

    assert compiled.resolve_column("سمت کاری") == "employees.position"
    assert compiled.value_aliases["در حال همکاری"] == ("employees.status", "active")
    assert compiled.metric_aliases["تعداد همکار فعال"] == "active_employee_count"


def test_resolver_enriches_intent_from_compiled_value_mapping() -> None:
    resolver = SemanticResolver()
    resolution = resolver._compiled_resolution("همکاران در حال همکاری", snapshot())
    intent = resolver.enrich_intent(QueryIntent(), resolution)

    assert intent.requested_entity == "employee"
    assert intent.status == "active"
    assert any(item.column == "status" and item.value == "active" for item in intent.filters)


def test_each_snapshot_is_immutable_and_versioned() -> None:
    semantic_snapshot = snapshot()

    assert semantic_snapshot.version == 12
    assert semantic_snapshot.catalog is semantic_snapshot.catalog


def test_review_service_supports_terms_values_joins_and_metrics() -> None:
    suggestions = SemanticSuggestionSet(
        tenant_id="test",
        source_fingerprint="fingerprint",
        generated_at="2026-01-01T00:00:00",
        tables=[SemanticTableSuggestion(
            name="employees", entity="employee", display_name_fa="کارمند",
            description_fa="کارمند", aliases_fa=["کارمند"],
        )],
    )
    service = SemanticReviewService()

    service._apply_business_term_review(suggestions, SemanticReviewRequest(
        target_type="business_term", table="employees", term_fa="پست",
        maps_to="employees.position", aliases_fa=["سمت"],
    ))
    service._apply_value_mapping_review(suggestions, SemanticReviewRequest(
        target_type="value_mapping", table="employees", term_fa="شاغل",
        maps_to="employees.status", value="active",
    ))
    service._apply_join_review(suggestions, SemanticReviewRequest(
        target_type="join", table="employees", from_table="employees",
        from_column="organization_unit_id", to_table="organization_units",
        to_column="id",
    ))
    service._apply_metric_review(suggestions, SemanticReviewRequest(
        target_type="metric", table="employees", metric_name="تعداد کارمند",
        expression="employees.id", aggregation="COUNT_DISTINCT",
    ), "employees")

    assert suggestions.business_terms[0].maps_to == "employees.position"
    assert suggestions.value_mappings[0].value == "active"
    assert suggestions.joins[0].to_table == "organization_units"
    assert suggestions.metrics[0].aggregation == "COUNT_DISTINCT"


def test_compiled_metric_renders_executable_deterministic_sql() -> None:
    plan = SQLPlan(
        required_tables=["employees"],
        selected_columns=["SEMANTIC_METRIC:active_employee_count"],
        filters=[{"column": "status", "operator": "=", "value": "active"}],
    )

    sql = render_template_sql(plan, catalog())

    assert sql == (
        "SELECT COUNT(DISTINCT employees.id) AS active_employee_count "
        "FROM employees WHERE employees.status = 'active'"
    )
