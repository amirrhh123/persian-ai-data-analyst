from __future__ import annotations

from time import perf_counter

from backend.semantic.context_index import SemanticContextIndexService
from backend.semantic.models import (
    SemanticCatalog,
    SemanticColumn,
    SemanticJoin,
    SemanticMetric,
    SemanticRule,
    SemanticTable,
)


def _catalog(version: int = 3) -> SemanticCatalog:
    return SemanticCatalog(
        version=version,
        tables=[
            SemanticTable(
                name="employees", entity="employee", description="کارمندان سازمان",
                aliases=["کارمند", "همکار"],
                columns=[
                    SemanticColumn(name="position", data_type="text", description="سمت سازمانی", aliases=["پست"]),
                    SemanticColumn(name="status", data_type="text", description="وضعیت همکاری", aliases=["وضعیت"]),
                ],
            ),
            SemanticTable(
                name="organization_units", entity="organization_unit", description="واحدهای سازمانی",
                aliases=["واحد سازمانی"],
                columns=[SemanticColumn(name="id", data_type="integer", description="شناسه", aliases=[])],
            ),
        ],
        business_terms=[{
            "term_fa": "عنوان شغلی", "aliases_fa": ["سمت کاری"],
            "maps_to": "employees.position", "description_fa": "سمت رسمی کارمند",
        }],
        value_mappings=[{
            "term_fa": "مشغول به کار", "aliases_fa": ["شاغل"],
            "column": "employees.status", "value": "active",
            "description_fa": "کارمند فعال",
        }],
        metrics=[SemanticMetric(
            name="employee_count", table="employees", expression="employees.id",
            aggregation="COUNT_DISTINCT", description="تعداد کارکنان", aliases=["تعداد همکار"],
        )],
        joins=[SemanticJoin(
            from_table="employees", from_column="organization_unit_id",
            to_table="organization_units", to_column="id", description="کارمند به واحد سازمانی وصل است",
        )],
        rules=[SemanticRule(
            name="employee_location", description="استان کارمند از واحد سازمانی خوانده می‌شود",
            applies_to=["employees", "organization_units"],
        )],
    )


def test_index_selects_business_term_value_and_metric_context() -> None:
    index = SemanticContextIndexService().build("demo", _catalog())

    position = index.search("عنوان شغلی کارمند", limit=5)
    active = index.search("تعداد همکار شاغل", limit=8)

    assert any(match.document.kind == "business_term" and match.document.target == "employees.position" for match in position)
    assert any(match.document.kind == "metric" and match.document.target == "employee_count" for match in active)
    assert any(match.document.kind == "value_mapping" and match.document.target == "employees.status" for match in active)


def test_index_is_cached_by_tenant_and_semantic_version() -> None:
    service = SemanticContextIndexService()

    first, first_built = service.get_or_build("demo", _catalog(version=3))
    second, second_built = service.get_or_build("demo", _catalog(version=3))
    third, third_built = service.get_or_build("demo", _catalog(version=4))

    assert first_built is True
    assert second_built is False
    assert first is second
    assert third_built is True
    assert third is not first


def test_index_query_is_fast_after_build() -> None:
    index = SemanticContextIndexService().build("demo", _catalog())
    started = perf_counter()

    for _ in range(200):
        index.search("پست کارمند شاغل", limit=10)

    assert perf_counter() - started < 1.0


def test_allowed_tables_remove_unrelated_join_context() -> None:
    index = SemanticContextIndexService().build("demo", _catalog())

    employee_only = index.search(
        "اطلاعات کارمند",
        allowed_tables={"employees"},
        limit=20,
    )

    assert all(match.document.kind != "join" for match in employee_only)
    assert all(match.document.kind != "rule" for match in employee_only)
