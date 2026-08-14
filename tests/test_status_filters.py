import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_inactive_is_not_misread_as_active():
    inactive_intent = extract_intent("اطلاعات کارمندان غیرفعال")
    active_intent = extract_intent("اطلاعات کارمندان فعال")

    assert inactive_intent.status == "inactive"
    assert active_intent.status == "active"


@pytest.mark.asyncio
async def test_active_students_by_province_keeps_status_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان فعال استان تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["status"] == "active"
    assert "organization_units.province = 'تهران'" in response.sql
    assert "students.status = 'active'" in response.sql
    assert "COUNT(students.id) AS student_count" in response.sql


@pytest.mark.asyncio
async def test_inactive_students_by_school_keeps_status_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزان غیرفعال مدرسه دبیرستان شهید بهشتی را نشان بده", execute=False)
    )

    assert response.valid is True
    assert response.intent["status"] == "inactive"
    assert response.intent["named_school"] == "دبیرستان شهید بهشتی"
    assert "schools.name = 'دبیرستان شهید بهشتی'" in response.sql
    assert "students.status = 'inactive'" in response.sql
    assert "COUNT(" not in response.sql


@pytest.mark.asyncio
async def test_active_employees_by_city_keeps_status_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات کارمندان فعال شهر تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["status"] == "active"
    assert "organization_units.city = 'تهران'" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "COUNT(" not in response.sql


@pytest.mark.asyncio
async def test_inactive_employee_count_uses_employee_status():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارمندان غیرفعال", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["status"] == "inactive"
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "employees.status = 'inactive'" in response.sql
