import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_city_count_uses_school_org_unit_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان شهر تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["city"] == "تهران"
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in response.sql
    assert "organization_units.city = 'تهران'" in response.sql


@pytest.mark.asyncio
async def test_student_city_list_uses_school_org_unit_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات دانش آموزان شهر تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["aggregation"] is None
    assert "COUNT(" not in response.sql
    assert "students.first_name" in response.sql
    assert "organization_units.city = 'تهران'" in response.sql


@pytest.mark.asyncio
async def test_employee_city_count_uses_org_unit_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارمندان شهر تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["city"] == "تهران"
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "JOIN organization_units ON employees.organization_unit_id = organization_units.id" in response.sql
    assert "organization_units.city = 'تهران'" in response.sql


@pytest.mark.asyncio
async def test_employee_city_list_uses_org_unit_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات کارمندان شهر تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["aggregation"] is None
    assert "COUNT(" not in response.sql
    assert "employees.first_name" in response.sql
    assert "organization_units.city = 'تهران'" in response.sql
