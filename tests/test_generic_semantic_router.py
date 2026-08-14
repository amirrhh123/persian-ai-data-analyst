from backend.pipeline.query_pipeline import query_pipeline
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticTable


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        tables=[
            SemanticTable(
                name="training_evaluations",
                entity="training_evaluation",
                description="ارزیابی‌های آموزشی",
                aliases=["ارزیابی آموزشی", "ارزیابی‌های آموزشی", "فرم ارزیابی دوره"],
                primary_key="id",
                default_display_columns=["course_name", "score"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="شناسه"),
                    SemanticColumn(name="course_name", data_type="text", description="نام دوره", aliases=["نام دوره"]),
                    SemanticColumn(name="score", data_type="integer", description="امتیاز"),
                ],
            )
        ]
    )


def test_generic_semantic_router_builds_count_plan_from_table_alias():
    plan = query_pipeline._semantic_table_plan("تعداد ارزیابی‌های آموزشی را بگو", _catalog())

    assert plan is not None
    assert plan.required_tables == ["training_evaluations"]
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]
    assert plan.aggregations == [{"function": "COUNT", "column": "training_evaluations.id"}]


def test_generic_semantic_router_builds_list_plan_from_table_alias():
    plan = query_pipeline._semantic_table_plan("اطلاعات فرم ارزیابی دوره را نشان بده", _catalog())

    assert plan is not None
    assert plan.required_tables == ["training_evaluations"]
    assert plan.selected_columns == ["GENERIC_TABLE_LIST", "course_name", "score"]


def test_generic_semantic_filter_extractor_uses_column_aliases():
    table = _catalog().table("training_evaluations")

    filters = query_pipeline._semantic_filters_for_table("تعداد ارزیابی‌های آموزشی با نام دوره ریاضی", table)

    assert filters == [{"column": "course_name", "operator": "=", "value": "ریاضی"}]
