import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_multiple_provinces_are_extracted_for_comparison():
    intent = extract_intent("مقایسه تعداد دانش آموزان تهران و اصفهان")

    assert intent.requested_entity == "student"
    assert intent.aggregation == "COUNT"
    assert intent.province is None
    assert intent.province_values == ["اصفهان", "تهران"]
    assert intent.grouping == ["province"]


@pytest.mark.asyncio
async def test_student_count_comparison_uses_province_in_and_group_by():
    response = await query_pipeline.execute(
        PipelineRequest(question="مقایسه تعداد دانش آموزان تهران و اصفهان", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["province_values"] == ["اصفهان", "تهران"]
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "organization_units.province IN ('اصفهان', 'تهران')" in response.sql
    assert "GROUP BY organization_units.province" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql


@pytest.mark.asyncio
async def test_employee_active_count_comparison_keeps_status():
    response = await query_pipeline.execute(
        PipelineRequest(question="مقایسه تعداد کارمندان فعال تهران و فارس و گیلان", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["status"] == "active"
    assert response.intent["province_values"] == ["تهران", "فارس", "گیلان"]
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "organization_units.province IN ('تهران', 'فارس', 'گیلان')" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "GROUP BY organization_units.province" in response.sql


@pytest.mark.asyncio
async def test_school_count_comparison_uses_distinct_school_count():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس استان تهران و اصفهان را مقایسه کن", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "school"
    assert response.intent["province_values"] == ["اصفهان", "تهران"]
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "organization_units.province IN ('اصفهان', 'تهران')" in response.sql
    assert "GROUP BY organization_units.province" in response.sql
