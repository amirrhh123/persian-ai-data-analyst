from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.sql.generator import sql_generator
from backend.sql.planner import SQLPlanner
from backend.sql.models import SQLPlan


def test_loader_prefers_active_semantic_catalog():
    catalog = load_tenant_semantic_catalog("education_ministry")

    assert catalog.table("employees").description == "اطلاعات پایه کارمندان و پرسنل سازمان."
    assert any(
        rule.name == "business_term_retirement_records_pension_amount"
        for rule in catalog.rules
    )


def test_sql_planner_uses_active_catalog_aliases():
    schema = DatabaseSchema(
        tables=[
            TableInfo(name="employees", columns=[ColumnInfo(name="id", data_type="integer")]),
            TableInfo(name="students", columns=[ColumnInfo(name="id", data_type="integer")]),
        ],
        relationships=[],
    )

    planner = SQLPlanner()

    assert planner.detect_tables("اطلاعات پرسنل را بده", schema, tenant_id="education_ministry") == ["employees"]
    assert planner.detect_tables("تعداد محصل ها", schema, tenant_id="education_ministry") == ["students"]


def test_sql_generator_prompt_includes_active_semantic_rules():
    schema = DatabaseSchema(
        tables=[
            TableInfo(
                name="retirement_records",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="pension_amount", data_type="numeric"),
                ],
            )
        ],
        relationships=[],
    )
    plan = SQLPlan(
        required_tables=["retirement_records"],
        selected_columns=["retirement_records.pension_amount"],
    )
    catalog = load_tenant_semantic_catalog("education_ministry")

    prompt = sql_generator._build_prompt(plan, schema, semantic_catalog=catalog)

    assert "business_term_retirement_records_pension_amount" in prompt
    assert "retirement_records.pension_amount" in prompt
    assert "سنوات" in prompt
