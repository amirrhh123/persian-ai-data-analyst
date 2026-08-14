import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_information_student_by_national_id_returns_profile_columns():
    response = await query_pipeline.execute(
        PipelineRequest(question='اطلاعات دانش آموز با کد ملی "3489881390"', execute=False)
    )

    assert response.valid is True
    assert response.intent["wants_full_profile"] is True
    assert "students.grade" in response.sql
    assert "students.status" in response.sql
    assert "students.school_id" in response.sql
    assert "students.enrollment_year" in response.sql


@pytest.mark.asyncio
async def test_information_school_by_name_returns_profile_columns():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات مدرسه دبیرستان شهید بهشتی", execute=False)
    )

    assert response.valid is True
    assert response.intent["wants_full_profile"] is True
    assert response.intent["named_school"] == "دبیرستان شهید بهشتی"
    assert "schools.phone" in response.sql
    assert "schools.address" in response.sql
    assert "schools.capacity" in response.sql
    assert "schools.established_year" in response.sql
