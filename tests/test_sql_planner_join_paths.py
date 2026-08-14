from backend.database.models import ColumnInfo, DatabaseSchema, RelationshipInfo, TableInfo
from backend.sql.planner import SQLPlanner


def _column(name: str) -> ColumnInfo:
    return ColumnInfo(name=name, data_type="integer")


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=[
            TableInfo(name="students", columns=[_column("id"), _column("school_id")]),
            TableInfo(name="schools", columns=[_column("id"), _column("organization_unit_id")]),
            TableInfo(name="organization_units", columns=[_column("id")]),
            TableInfo(name="employees", columns=[_column("id"), _column("organization_unit_id")]),
            TableInfo(name="salary_items", columns=[_column("id"), _column("employee_id")]),
        ],
        relationships=[
            RelationshipInfo(
                source_table="employees",
                source_column="organization_unit_id",
                target_table="organization_units",
                target_column="id",
            ),
            RelationshipInfo(
                source_table="schools",
                source_column="organization_unit_id",
                target_table="organization_units",
                target_column="id",
            ),
            RelationshipInfo(
                source_table="students",
                source_column="school_id",
                target_table="schools",
                target_column="id",
            ),
            RelationshipInfo(
                source_table="salary_items",
                source_column="employee_id",
                target_table="employees",
                target_column="id",
            ),
        ]
    )


def test_expand_required_tables_adds_intermediate_join_table():
    planner = SQLPlanner()

    tables = planner.expand_required_tables(["students", "organization_units"], _schema().relationships)

    assert tables == ["students", "organization_units", "schools"]


def test_detect_joins_finds_multi_hop_student_to_organization_unit_path():
    planner = SQLPlanner()

    joins = planner.detect_joins(["students", "organization_units"], _schema().relationships)

    assert {
        "from_table": "students",
        "from_column": "school_id",
        "to_table": "schools",
        "to_column": "id",
    } in joins
    assert {
        "from_table": "schools",
        "from_column": "organization_unit_id",
        "to_table": "organization_units",
        "to_column": "id",
    } in joins


def test_detect_joins_finds_multi_hop_salary_to_organization_unit_path():
    planner = SQLPlanner()

    joins = planner.detect_joins(["salary_items", "organization_units"], _schema().relationships)

    assert {
        "from_table": "salary_items",
        "from_column": "employee_id",
        "to_table": "employees",
        "to_column": "id",
    } in joins
    assert {
        "from_table": "employees",
        "from_column": "organization_unit_id",
        "to_table": "organization_units",
        "to_column": "id",
    } in joins


def test_create_plan_keeps_intermediate_tables_in_required_tables():
    planner = SQLPlanner()

    plan = planner.create_plan("students organization_units", _schema())

    assert "students" in plan.required_tables
    assert "organization_units" in plan.required_tables
    assert "schools" in plan.required_tables
