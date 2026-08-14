import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_employee_full_profile_can_be_found_by_full_name():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات کارمند علی احمدی", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["wants_full_profile"] is True
    assert response.intent["first_name"] == "علی"
    assert response.intent["last_name"] == "احمدی"
    assert "employees.first_name = 'علی'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql
    assert "employees.national_id" in response.sql
    assert "employees.organization_unit_id" in response.sql
    assert "employees.hire_date" in response.sql
    assert "employees.created_at" in response.sql


@pytest.mark.asyncio
async def test_student_full_profile_can_be_found_by_full_name():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات دانش آموز پوریا محمدی", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["wants_full_profile"] is True
    assert response.intent["first_name"] == "پوریا"
    assert response.intent["last_name"] == "محمدی"
    assert "students.first_name = 'پوریا'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "students.national_id" in response.sql
    assert "students.school_id" in response.sql
    assert "students.enrollment_year" in response.sql


@pytest.mark.asyncio
async def test_employee_requested_column_can_be_found_by_full_name():
    response = await query_pipeline.execute(
        PipelineRequest(question="شغل کارمند علی احمدی چیست", execute=False)
    )

    assert response.valid is True
    assert response.intent["first_name"] == "علی"
    assert response.intent["last_name"] == "احمدی"
    assert "position" in response.intent["requested_columns"]
    assert "employees.position" in response.sql
    assert "employees.first_name = 'علی'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql


@pytest.mark.asyncio
async def test_student_requested_column_can_be_found_by_full_name():
    response = await query_pipeline.execute(
        PipelineRequest(question="کد ملی دانش آموز پوریا محمدی را بگو", execute=False)
    )

    assert response.valid is True
    assert response.intent["first_name"] == "پوریا"
    assert response.intent["last_name"] == "محمدی"
    assert "national_id" in response.intent["requested_columns"]
    assert "students.national_id" in response.sql
    assert "students.first_name = 'پوریا'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
