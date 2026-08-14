import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_grouping_terms_are_detected_for_province_and_city():
    province_intent = extract_intent("تعداد دانش آموزان به تفکیک استان")
    city_intent = extract_intent("تعداد مدارس به تفکیک شهر")

    assert province_intent.grouping == ["province"]
    assert city_intent.grouping == ["city"]


@pytest.mark.asyncio
async def test_student_count_grouped_by_province_uses_correct_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان به تفکیک استان", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["grouping"] == ["province"]
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in response.sql
    assert "GROUP BY organization_units.province" in response.sql
    assert "ORDER BY student_count DESC" in response.sql


@pytest.mark.asyncio
async def test_active_student_count_grouped_by_city_keeps_status():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان فعال به تفکیک شهر", execute=False)
    )

    assert response.valid is True
    assert response.intent["grouping"] == ["city"]
    assert response.intent["status"] == "active"
    assert "GROUP BY organization_units.city" in response.sql
    assert "students.status = 'active'" in response.sql


@pytest.mark.asyncio
async def test_employee_count_grouped_by_province_uses_org_units():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارمندان هر استان", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["grouping"] == ["province"]
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "JOIN organization_units ON employees.organization_unit_id = organization_units.id" in response.sql
    assert "GROUP BY organization_units.province" in response.sql


@pytest.mark.asyncio
async def test_school_count_grouped_by_city_uses_school_id():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس به تفکیک شهر", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "school"
    assert response.intent["grouping"] == ["city"]
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in response.sql
    assert "GROUP BY organization_units.city" in response.sql
