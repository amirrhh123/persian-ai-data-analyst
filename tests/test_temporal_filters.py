import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_persian_year_and_month_are_extracted_for_salary_questions():
    intent = extract_intent("میانگین حقوق سال ۱۴۰۳ ماه ۷")

    assert intent.requested_entity == "salary"
    assert intent.date_range == {"year": 1403, "month": 7}


def test_persian_month_name_is_extracted():
    intent = extract_intent("میانگین پرداختی مهر سال ۱۴۰۲")

    assert intent.requested_entity == "salary"
    assert intent.date_range == {"year": 1402, "month": 7}


@pytest.mark.asyncio
async def test_salary_average_by_year_uses_salary_year_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="میانگین حقوق سال ۱۴۰۳", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "salary"
    assert response.intent["date_range"] == {"year": 1403, "month": None}
    assert "AVG(salary_items.base_salary)" in response.sql
    assert "salary_items.year = 1403" in response.sql


@pytest.mark.asyncio
async def test_salary_average_by_year_and_month_uses_both_filters():
    response = await query_pipeline.execute(
        PipelineRequest(question="میانگین حقوق مهر سال ۱۴۰۲", execute=False)
    )

    assert response.valid is True
    assert response.intent["date_range"] == {"year": 1402, "month": 7}
    assert "salary_items.year = 1402" in response.sql
    assert "salary_items.month = 7" in response.sql


@pytest.mark.asyncio
async def test_highest_salary_by_year_keeps_ranking_and_year_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="برای کدام کارمند بیشترین حقوق سال ۱۴۰۳ پرداخت شده؟", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "salary"
    assert response.intent["date_range"] == {"year": 1403, "month": None}
    assert "SUM(salary_items.allowances) AS total_salary" in response.sql
    assert "salary_items.year = 1403" in response.sql
    assert "ORDER BY total_salary DESC" in response.sql
    assert "LIMIT 1" in response.sql
