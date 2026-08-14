import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_top_n_grouped_student_intent_is_detected():
    intent = extract_intent("۵ استان با بیشترین تعداد دانش آموز")

    assert intent.requested_entity == "student"
    assert intent.aggregation == "COUNT"
    assert intent.grouping == ["province"]
    assert intent.sorting is not None
    assert intent.sorting.direction == "DESC"
    assert intent.limit == 5


def test_bottom_n_grouped_employee_intent_is_detected():
    intent = extract_intent("۳ شهر با کمترین تعداد کارمند")

    assert intent.requested_entity == "employee"
    assert intent.aggregation == "COUNT"
    assert intent.grouping == ["city"]
    assert intent.sorting is not None
    assert intent.sorting.direction == "ASC"
    assert intent.limit == 3


@pytest.mark.asyncio
async def test_top_student_provinces_sql_orders_and_limits():
    response = await query_pipeline.execute(
        PipelineRequest(question="۵ استان با بیشترین تعداد دانش آموز", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "GROUP BY organization_units.province" in response.sql
    assert "ORDER BY student_count DESC" in response.sql
    assert "LIMIT 5" in response.sql


@pytest.mark.asyncio
async def test_bottom_employee_cities_sql_orders_and_limits():
    response = await query_pipeline.execute(
        PipelineRequest(question="۳ شهر با کمترین تعداد کارمند", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "GROUP BY organization_units.city" in response.sql
    assert "ORDER BY employee_count ASC" in response.sql
    assert "LIMIT 3" in response.sql


@pytest.mark.asyncio
async def test_top_school_provinces_sql_uses_distinct_school_count():
    response = await query_pipeline.execute(
        PipelineRequest(question="۱۰ استان با بیشترین تعداد مدارس", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "school"
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "GROUP BY organization_units.province" in response.sql
    assert "ORDER BY school_count DESC" in response.sql
    assert "LIMIT 10" in response.sql
