import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_multiple_cities_are_extracted_for_comparison():
    intent = extract_intent("مقایسه تعداد مدارس شهر تهران و شهر ری")

    assert intent.requested_entity == "school"
    assert intent.aggregation == "COUNT"
    assert intent.province_values == []
    assert intent.city is None
    assert intent.city_values == ["تهران", "ری"]
    assert intent.grouping == ["city"]


@pytest.mark.asyncio
async def test_school_count_city_comparison_uses_city_in_and_group_by():
    response = await query_pipeline.execute(
        PipelineRequest(question="مقایسه تعداد مدارس شهر تهران و شهر ری", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "school"
    assert response.intent["city_values"] == ["تهران", "ری"]
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "organization_units.city IN ('تهران', 'ری')" in response.sql
    assert "GROUP BY organization_units.city" in response.sql


@pytest.mark.asyncio
async def test_student_count_city_comparison_uses_student_school_org_path():
    response = await query_pipeline.execute(
        PipelineRequest(question="مقایسه تعداد دانش آموزان شهر تهران و شهر شیراز", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["city_values"] == ["تهران", "شیراز"]
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "organization_units.city IN ('تهران', 'شیراز')" in response.sql
    assert "GROUP BY organization_units.city" in response.sql


@pytest.mark.asyncio
async def test_active_employee_city_comparison_keeps_status():
    response = await query_pipeline.execute(
        PipelineRequest(question="مقایسه تعداد کارمندان فعال شهر تهران و شهر مشهد", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["status"] == "active"
    assert response.intent["city_values"] == ["تهران", "مشهد"]
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "organization_units.city IN ('تهران', 'مشهد')" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "GROUP BY organization_units.city" in response.sql
