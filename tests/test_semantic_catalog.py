from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.database.schema_loader import schema_loader
from backend.semantic import load_tenant_semantic_catalog
from backend.sql.planner import SQLPlanner


def test_semantic_catalog_loads_core_entities():
    semantic_catalog = load_tenant_semantic_catalog()
    assert semantic_catalog.version == 1
    assert semantic_catalog.table("employees").entity == "employee"
    assert semantic_catalog.table("students").entity == "student"
    assert semantic_catalog.table("schools").entity == "school"
    assert semantic_catalog.table("organization_units").entity == "organization_unit"


def test_semantic_catalog_documents_text_identifiers():
    semantic_catalog = load_tenant_semantic_catalog()
    employee_national_id = semantic_catalog.table("employees").column("national_id")

    assert employee_national_id is not None
    assert employee_national_id.value_type == "text_identifier"
    assert employee_national_id.pii is True
    assert "کد ملی" in employee_national_id.aliases


def test_sql_planner_uses_semantic_table_aliases():
    schema = DatabaseSchema(
        tables=[
            TableInfo(name="employees", columns=[ColumnInfo(name="id", data_type="integer")]),
            TableInfo(name="schools", columns=[ColumnInfo(name="id", data_type="integer")]),
            TableInfo(name="students", columns=[ColumnInfo(name="id", data_type="integer")]),
        ],
        relationships=[],
    )

    planner = SQLPlanner()

    assert planner.detect_tables("اطلاعات کارمند با کد ملی را بده", schema) == ["employees"]
    assert planner.detect_tables("شماره تلفن دبیرستان شهید بهشتی", schema) == ["schools"]
    assert planner.detect_tables("تعداد دانش‌آموزان استان تهران", schema) == ["students"]


def test_semantic_catalog_matches_live_schema_columns():
    semantic_catalog = load_tenant_semantic_catalog()
    schema = schema_loader.load_full_schema()
    live_tables = {table.name: {column.name for column in table.columns} for table in schema.tables}

    for semantic_table in semantic_catalog.tables:
        assert semantic_table.name in live_tables
        semantic_columns = {column.name for column in semantic_table.columns}
        assert semantic_columns.issubset(live_tables[semantic_table.name])
