from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
import pytest
from backend.pipeline.query_pipeline import QueryPipeline
from backend.pipeline.models import PipelineRequest
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticJoin, SemanticTable


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        tables=[
            SemanticTable(
                name="orders",
                entity="order",
                description="سفارش‌های ثبت شده",
                aliases=["سفارش", "سفارش‌ها", "سفارش ها"],
                primary_key="id",
                default_display_columns=["id", "amount"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="شناسه", aliases=["شناسه"]),
                    SemanticColumn(name="name", data_type="character varying", description="نام سفارش", aliases=["نام"]),
                    SemanticColumn(name="customer_id", data_type="integer", description="مشتری"),
                    SemanticColumn(name="amount", data_type="integer", description="مبلغ", aliases=["مبلغ"]),
                    SemanticColumn(name="created_at", data_type="timestamp without time zone", description="تاریخ ثبت", aliases=["تاریخ ثبت", "تاریخ ایجاد"]),
                ],
            ),
            SemanticTable(
                name="customers",
                entity="customer",
                description="مشتریان",
                aliases=["مشتری", "مشتریان"],
                primary_key="id",
                default_display_columns=["id", "province"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="شناسه"),
                    SemanticColumn(name="name", data_type="character varying", description="نام مشتری", aliases=["نام", "نام مشتری"]),
                    SemanticColumn(name="province", data_type="character varying", description="استان", aliases=["استان"]),
                    SemanticColumn(name="score", data_type="integer", description="امتیاز مشتری", aliases=["امتیاز", "امتیاز مشتری"]),
                ],
            ),
            SemanticTable(
                name="agents",
                entity="agent",
                description="نمایندگان فروش",
                aliases=["نماینده", "نمایندگان"],
                primary_key="id",
                default_display_columns=["id", "score"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="شناسه"),
                    SemanticColumn(name="score", data_type="integer", description="امتیاز نماینده", aliases=["امتیاز", "امتیاز نماینده"]),
                ],
            ),
        ],
        joins=[
            SemanticJoin(
                from_table="orders",
                from_column="customer_id",
                to_table="customers",
                to_column="id",
                description="هر سفارش مربوط به یک مشتری است.",
            ),
            SemanticJoin(
                from_table="orders",
                from_column="agent_id",
                to_table="agents",
                to_column="id",
                description="هر سفارش می‌تواند یک نماینده فروش داشته باشد.",
            )
        ],
    )


def _discovery() -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="test",
        database_name="test",
        generated_at="2026-07-25T00:00:00",
        fingerprint="test",
        tables=[
            DiscoveredTableInfo(
                name="orders",
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(name="name", data_type="character varying", udt_name="varchar"),
                    DiscoveredColumnInfo(name="customer_id", data_type="integer", udt_name="int4"),
                    DiscoveredColumnInfo(name="agent_id", data_type="integer", udt_name="int4"),
                    DiscoveredColumnInfo(name="amount", data_type="integer", udt_name="int4"),
                    DiscoveredColumnInfo(name="created_at", data_type="timestamp without time zone", udt_name="timestamp"),
                ],
            ),
            DiscoveredTableInfo(
                name="customers",
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(name="name", data_type="character varying", udt_name="varchar"),
                    DiscoveredColumnInfo(
                        name="province",
                        data_type="character varying",
                        udt_name="varchar",
                        sample_values=[ColumnSampleValue(value="تهران", count=10)],
                    ),
                    DiscoveredColumnInfo(name="score", data_type="integer", udt_name="int4"),
                ],
            ),
            DiscoveredTableInfo(
                name="agents",
                columns=[
                    DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True),
                    DiscoveredColumnInfo(name="score", data_type="integer", udt_name="int4"),
                ],
            ),
        ],
    )


def test_semantic_table_plan_adds_related_table_filter_and_join(monkeypatch):
    pipeline = QueryPipeline()
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    plan = pipeline._semantic_table_plan("تعداد سفارش ها استان تهران", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders", "customers"]
    assert {
        "from_table": "orders",
        "from_column": "customer_id",
        "to_table": "customers",
        "to_column": "id",
    } in plan.joins
    assert {"column": "customers.province", "operator": "=", "value": "تهران"} in plan.filters
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]


def test_semantic_table_plan_adds_related_numeric_filter_and_join(monkeypatch):
    pipeline = QueryPipeline()
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    plan = pipeline._semantic_table_plan("تعداد سفارش ها با امتیاز مشتری بالای ۸۰", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders", "customers"]
    assert {
        "from_table": "orders",
        "from_column": "customer_id",
        "to_table": "customers",
        "to_column": "id",
    } in plan.joins
    assert {"column": "customers.score", "operator": ">", "value": "80"} in plan.filters
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]


def test_ambiguous_related_numeric_filter_is_not_added(monkeypatch):
    pipeline = QueryPipeline()
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    plan = pipeline._semantic_table_plan("تعداد سفارش ها با امتیاز بالای ۸۰", _catalog())

    assert plan is not None
    assert pipeline._last_related_ambiguity == {
        "type": "related_numeric_filter",
        "items": [
            {
                "operator": ">",
                "value": "80",
                "column": "score",
                "tables": ["agents", "customers"],
            }
        ],
    }
    assert {"column": "customers.score", "operator": ">", "value": "80"} not in plan.filters
    assert {"column": "agents.score", "operator": ">", "value": "80"} not in plan.filters
    assert "customers" not in plan.required_tables
    assert "agents" not in plan.required_tables


@pytest.mark.asyncio
async def test_execute_returns_clarification_for_ambiguous_related_numeric_filter(monkeypatch):
    import backend.pipeline.query_pipeline as query_pipeline_module

    pipeline = QueryPipeline()
    monkeypatch.setattr(query_pipeline_module, "load_tenant_semantic_catalog", lambda tenant_id=None: _catalog())
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    response = await pipeline.execute(PipelineRequest(question="تعداد سفارش ها با امتیاز بالای ۸۰", execute=False))

    assert response.success is False
    assert response.needs_clarification is True
    assert response.valid is False
    assert response.sql is None
    assert "score" in response.clarification_question
    assert "agents" in response.clarification_question
    assert "customers" in response.clarification_question


def test_semantic_table_plan_adds_related_group_by_column_and_join(monkeypatch):
    pipeline = QueryPipeline()
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    plan = pipeline._semantic_table_plan("تعداد سفارش ها به تفکیک استان", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders", "customers"]
    assert {
        "from_table": "orders",
        "from_column": "customer_id",
        "to_table": "customers",
        "to_column": "id",
    } in plan.joins
    assert plan.group_by == ["customers.province"]
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]


def test_semantic_table_plan_adds_numeric_average_aggregation():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("میانگین مبلغ سفارش ها", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders"]
    assert plan.selected_columns == ["GENERIC_TABLE_AGGREGATE"]
    assert plan.aggregations == [{"function": "AVG", "column": "amount"}]


def test_semantic_table_plan_adds_numeric_sum_with_related_group_by(monkeypatch):
    pipeline = QueryPipeline()
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    plan = pipeline._semantic_table_plan("مجموع مبلغ سفارش ها به تفکیک استان", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders", "customers"]
    assert plan.selected_columns == ["GENERIC_TABLE_AGGREGATE"]
    assert plan.aggregations == [{"function": "SUM", "column": "amount"}]
    assert plan.group_by == ["customers.province"]


def test_semantic_table_plan_adds_max_aggregation():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("بیشترین مبلغ سفارش ها", _catalog())

    assert plan is not None
    assert plan.selected_columns == ["GENERIC_TABLE_AGGREGATE"]
    assert plan.aggregations == [{"function": "MAX", "column": "amount"}]


def test_semantic_table_plan_adds_ranked_row_query():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("گران‌ترین سفارش کدام است؟", _catalog())

    assert plan is not None
    assert plan.selected_columns == ["GENERIC_TABLE_LIST", "id", "amount"]
    assert plan.order_by == "amount DESC"
    assert plan.limit == 1


def test_semantic_table_plan_adds_temporal_year_filter():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("تعداد سفارش ها در سال ۲۰۲۶", _catalog())

    assert plan is not None
    assert {"column": "created_at", "operator": "YEAR=", "value": "2026"} in plan.filters
    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]


def test_semantic_table_plan_uses_requested_columns_for_list_query():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("شناسه و مبلغ سفارش ها را نشان بده", _catalog())

    assert plan is not None
    assert plan.selected_columns == ["GENERIC_TABLE_LIST", "id", "amount"]


def test_semantic_table_plan_adds_related_requested_column_and_join():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("مبلغ سفارش ها و استان مشتری را نشان بده", _catalog())

    assert plan is not None
    assert plan.required_tables == ["orders", "customers"]
    assert "amount" in plan.selected_columns
    assert "customers.province" in plan.selected_columns
    assert {
        "from_table": "orders",
        "from_column": "customer_id",
        "to_table": "customers",
        "to_column": "id",
    } in plan.joins


def test_ambiguous_requested_column_is_not_selected():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("نام سفارش ها را نشان بده", _catalog())

    assert plan is not None
    assert pipeline._last_related_ambiguity == {
        "type": "requested_column",
        "items": [{"label": "نام", "columns": ["name", "customers.name"]}],
    }
    assert "name" not in plan.selected_columns
    assert "customers.name" not in plan.selected_columns


@pytest.mark.asyncio
async def test_execute_returns_clarification_for_ambiguous_requested_column(monkeypatch):
    import backend.pipeline.query_pipeline as query_pipeline_module

    pipeline = QueryPipeline()
    monkeypatch.setattr(query_pipeline_module, "load_tenant_semantic_catalog", lambda tenant_id=None: _catalog())
    monkeypatch.setattr(pipeline, "_load_discovery_snapshot", lambda tenant_id=None: _discovery())

    response = await pipeline.execute(PipelineRequest(question="نام سفارش ها را نشان بده", execute=False))

    assert response.success is False
    assert response.needs_clarification is True
    assert response.sql is None
    assert "نام" in response.clarification_question
    assert "customers.name" in response.clarification_question


def test_semantic_table_plan_adds_current_year_temporal_filter():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("تعداد سفارش های امسال", _catalog())

    assert plan is not None
    assert {"column": "created_at", "operator": "YEAR_CURRENT", "value": ""} in plan.filters


def test_semantic_table_plan_adds_recent_days_temporal_filter():
    pipeline = QueryPipeline()

    plan = pipeline._semantic_table_plan("تعداد سفارش های ۳۰ روز اخیر", _catalog())

    assert plan is not None
    assert {"column": "created_at", "operator": "DAYS_AGO", "value": "30"} in plan.filters
