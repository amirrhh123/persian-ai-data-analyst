import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_school_count_province_type_and_capacity_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد مدارس دولتی استان تهران با ظرفیت بالای ۵۰۰",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "school"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["province"] == "تهران"
    assert response.intent["school_type"] == "دولتی"
    assert response.intent["capacity_min"] == 500
    assert response.sql is not None
    assert "organization_units.province = 'تهران'" in response.sql
    assert "schools.school_type = 'دولتی'" in response.sql
    assert "schools.capacity >= 500" in response.sql
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_school_list_city_type_and_established_year_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="اسم دبیرستان های شهر تهران که سال تاسیس ۱۳۹۰ هستند",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "school"
    assert response.intent["city"] == "تهران"
    assert response.intent["school_type"] == "دبیرستان"
    assert response.intent["established_year"] == 1390
    assert response.sql is not None
    assert "organization_units.city = 'تهران'" in response.sql
    assert "schools.school_type = 'دبیرستان'" in response.sql
    assert "schools.established_year = 1390" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_school_count_can_filter_by_type_without_location():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد مدارس نمونه دولتی",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "school"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["school_type"] == "نمونه دولتی"
    assert response.sql is not None
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "schools.school_type = 'نمونه دولتی'" in response.sql
    assert response.valid, response.errors

