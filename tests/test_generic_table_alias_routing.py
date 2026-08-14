from backend.pipeline.query_pipeline import QueryPipeline
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticTable


def test_manual_table_alias_routes_record_count_to_generic_table():
    catalog = SemanticCatalog(
        tables=[
            SemanticTable(
                name="test1",
                entity="test1",
                description="test table",
                aliases=["\u062c\u062f\u0648\u0644 \u062a\u0633\u062a"],
                primary_key="id",
                default_display_columns=["id"],
                columns=[SemanticColumn(name="id", data_type="integer", description="id")],
            )
        ],
        joins=[],
    )

    plan = QueryPipeline()._semantic_table_plan(
        "\u062a\u0639\u062f\u0627\u062f \u0631\u06a9\u0648\u0631\u062f \u0647\u0627\u06cc \u062c\u062f\u0648\u0644 \u062a\u0633\u062a",
        catalog,
    )

    assert plan is not None
    assert plan.required_tables == ["test1"]
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]
    assert plan.aggregations == [{"function": "COUNT", "column": "test1.id"}]


def test_table_name_with_persian_digit_matches_ascii_table_name():
    catalog = SemanticCatalog(
        tables=[
            SemanticTable(
                name="test1",
                entity="test1",
                description="test table",
                aliases=["test1"],
                primary_key="id",
                default_display_columns=["id"],
                columns=[SemanticColumn(name="id", data_type="integer", description="id")],
            )
        ],
        joins=[],
    )

    plan = QueryPipeline()._semantic_table_plan(
        "\u0631\u06a9\u0648\u0631\u062f \u0647\u0627\u06cc \u062c\u062f\u0648\u0644 test\u06f1",
        catalog,
    )

    assert plan is not None
    assert plan.required_tables == ["test1"]
