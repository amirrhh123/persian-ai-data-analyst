from backend.sql.models import SQLPlan
from backend.sql.templates import render_template_sql


def test_student_list_by_province_template_uses_required_join_path():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        selected_columns=["STUDENT_LIST_BY_PROVINCE"],
        filters=[{"column": "province", "operator": "=", "value": "تهران"}],
    )

    sql = render_template_sql(plan)

    assert "FROM students" in sql
    assert "JOIN schools ON students.school_id = schools.id" in sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in sql
    assert "organization_units.province = 'تهران'" in sql
    assert "schools.name LIKE" not in sql
    assert "ORDER BY students.id" in sql
