import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_identity_by_quoted_national_id():
    response = await query_pipeline.execute(
        PipelineRequest(question='نام دانش آموز با کد ملی "3489881390"', execute=False)
    )

    assert response.group == "student"
    assert response.report == "student_list"
    assert response.valid is True
    assert response.intent["national_id"] == "3489881390"
    assert response.intent["named_student"] is None
    assert "FROM students" in response.sql
    assert "students.national_id = '3489881390'" in response.sql
    assert "students.national_id = 3489881390" not in response.sql
def test_student_school_name_lookup_uses_school_id_join():
    # The national-id lookup must resolve students.school_id through schools.id.
    from backend.sql.models import SQLPlan
    from backend.sql.templates import render_template_sql

    plan = SQLPlan(
        required_tables=["students", "schools"],
        selected_columns=["STUDENT_BY_NATIONAL_ID", "first_name", "last_name", "school_name"],
        filters=[{"column": "national_id", "operator": "=", "value": "1034567890"}],
    )
    sql = render_template_sql(plan) or ""
    assert "JOIN schools ON students.school_id = schools.id" in sql
    assert "schools.name AS school_name" in sql
    assert "students.national_id = '1034567890'" in sql
