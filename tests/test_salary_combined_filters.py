import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_salary_average_combines_year_province_status_and_position():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="میانگین حقوق سال ۱۴۰۳ کارمندان فعال استان تهران با شغل دبیر",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "salary"
    assert response.intent["date_range"]["year"] == 1403
    assert response.intent["province"] == "تهران"
    assert response.intent["status"] == "active"
    assert response.intent["position"] == "دبیر"
    assert response.sql is not None
    assert "JOIN employees ON salary_items.employee_id = employees.id" in response.sql
    assert "JOIN organization_units ON employees.organization_unit_id = organization_units.id" in response.sql
    assert "salary_items.year = 1403" in response.sql
    assert "organization_units.province = 'تهران'" in response.sql
    assert "employees.status = 'active'" in response.sql
    assert "employees.position = 'دبیر'" in response.sql
    assert "AVG(salary_items.net_salary)" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_highest_salary_combines_month_year_and_city():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="برای کدام کارمند بیشترین حقوق مهر سال ۱۴۰۲ شهر اصفهان پرداخت شده؟",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "salary"
    assert response.intent["date_range"]["year"] == 1402
    assert response.intent["date_range"]["month"] == 7
    assert response.intent["city"] == "اصفهان"
    assert response.sql is not None
    assert "salary_items.year = 1402" in response.sql
    assert "salary_items.month = 7" in response.sql
    assert "organization_units.city = 'اصفهان'" in response.sql
    assert "ORDER BY total_salary DESC" in response.sql
    assert "LIMIT 1" in response.sql
    assert response.valid, response.errors


@pytest.mark.asyncio
async def test_salary_average_can_filter_by_employee_national_id():
    response = await query_pipeline.execute(
        PipelineRequest(
            question='میانگین حقوق کارمند با کد ملی "4871587050" در سال ۱۴۰۳',
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "salary"
    assert response.intent["national_id"] == "4871587050"
    assert response.intent["date_range"]["year"] == 1403
    assert response.sql is not None
    assert "employees.national_id = '4871587050'" in response.sql
    assert "salary_items.year = 1403" in response.sql
    assert response.valid, response.errors

