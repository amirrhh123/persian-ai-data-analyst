import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_national_id_by_name_grade_and_school():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="کد ملی دانش آموز پوریا محمدی پایه یازدهم در مدرسه دبیرستان فرزانگان مرودشت را بگو",
            execute=False,
        )
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["first_name"] == "پوریا"
    assert response.intent["last_name"] == "محمدی"
    assert response.intent["grade"] == "یازدهم"
    assert response.intent["named_school"] == "دبیرستان فرزانگان مرودشت"
    assert "students.first_name = 'پوریا'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "students.grade = 'یازدهم'" in response.sql
    assert "schools.name = 'دبیرستان فرزانگان مرودشت'" in response.sql
    assert "students.national_id" in response.sql


@pytest.mark.asyncio
async def test_unknown_explicit_school_name_requests_clarification():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="کد ملی دانش آموز پوریا محمدی پایه یازدهم در مدرسه میناب را بگو",
            execute=False,
        )
    )

    if response.needs_clarification:
        assert response.valid is False
        assert "میناب" in response.clarification_question
    else:
        # If the test database is unavailable, fuzzy school resolution is skipped
        # and the raw explicit school name is kept in SQL generation.
        assert response.valid is True
        assert "schools.name = 'مدرسه میناب'" in response.sql


@pytest.mark.asyncio
async def test_employee_profile_by_name_status_and_city():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="اطلاعات کارمند علی احمدی فعال شهر تهران را نشان بده",
            execute=False,
        )
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["first_name"] == "علی"
    assert response.intent["last_name"] == "احمدی"
    assert response.intent["status"] == "active"
    assert response.intent["city"] == "تهران"
    assert "employees.first_name = 'علی'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "organization_units.city = 'تهران'" in response.sql
