import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_school_name_can_be_found_by_student_name_and_grade():
    response = await query_pipeline.execute(
        PipelineRequest(question="نام مدرسه دانش آموز پوریا محمدی پایه یازدهم", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["wants_school_name"] is True
    assert response.intent["named_school"] is None
    assert response.intent["first_name"] == "پوریا"
    assert response.intent["last_name"] == "محمدی"
    assert response.intent["grade"] == "یازدهم"
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "schools.name AS school_name" in response.sql
    assert "students.first_name = 'پوریا'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "students.grade = 'یازدهم'" in response.sql
