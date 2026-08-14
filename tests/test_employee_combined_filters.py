import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_employee_status_position_and_province_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد کارمندان فعال استان تهران با شغل دبیر",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "employee"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["province"] == "تهران"
    assert response.intent["status"] == "active"
    assert response.intent["position"] == "دبیر"
    assert response.sql is not None
    assert "organization_units.province = 'تهران'" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "employees.position = 'دبیر'" in response.sql
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_employee_city_last_name_position_and_hire_year_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="کارمندان شهر اصفهان که فامیلشان محمدی است و شغل کارشناس دارند و سال استخدام ۱۴۰۱ هستند",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "employee"
    assert response.intent["city"] == "اصفهان"
    assert response.intent["last_name"] == "محمدی"
    assert response.intent["position"] == "کارشناس"
    assert response.intent["hire_year"] == 1401
    assert response.sql is not None
    assert "organization_units.city = 'اصفهان'" in response.sql
    assert "employees.last_name = 'محمدی'" in response.sql
    assert "employees.position = 'کارشناس'" in response.sql
    assert "EXTRACT(YEAR FROM employees.hire_date) = 1401" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_employee_count_can_filter_by_position_without_location():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد کارمندان با سمت مدیر",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "employee"
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["position"] == "مدیر"
    assert response.sql is not None
    assert "COUNT(employees.id) AS total_employees" in response.sql
    assert "employees.position = 'مدیر'" in response.sql
    assert response.valid, response.errors

