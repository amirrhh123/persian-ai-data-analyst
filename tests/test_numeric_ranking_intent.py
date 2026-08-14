import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_lowest_paid_service_years_targets_pension_amount():
    intent = extract_intent("برای کدام کارمند کمترین سنوات پرداخت شده؟")

    assert intent.requested_entity == "retirement"
    assert intent.ranking_metric == "pension_amount"
    assert intent.sorting is not None
    assert intent.sorting.direction == "ASC"
    assert intent.sorting.column == "retirement_records.pension_amount"
    assert intent.limit == 1


def test_highest_paid_service_years_targets_pension_amount():
    intent = extract_intent("برای کدام کارمند بیشترین سنوات پرداخت شده؟")

    assert intent.requested_entity == "retirement"
    assert intent.ranking_metric == "pension_amount"
    assert intent.sorting is not None
    assert intent.sorting.direction == "DESC"
    assert intent.sorting.column == "retirement_records.pension_amount"
    assert intent.limit == 1


@pytest.mark.asyncio
async def test_lowest_paid_service_years_sql_uses_retirement_records():
    response = await query_pipeline.execute(
        PipelineRequest(question="برای کدام کارمند کمترین سنوات پرداخت شده؟", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "retirement"
    assert response.intent["ranking_metric"] == "pension_amount"
    assert "FROM retirement_records" in response.sql
    assert "JOIN employees ON retirement_records.employee_id = employees.id" in response.sql
    assert "retirement_records.pension_amount" in response.sql
    assert "ORDER BY retirement_records.pension_amount ASC" in response.sql
    assert "LIMIT 1" in response.sql
    assert "AVG(" not in response.sql
    assert "salary_items" not in response.sql


@pytest.mark.asyncio
async def test_highest_paid_service_years_sql_uses_retirement_records():
    response = await query_pipeline.execute(
        PipelineRequest(question="برای کدام کارمند بیشترین سنوات پرداخت شده؟", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "retirement"
    assert response.intent["ranking_metric"] == "pension_amount"
    assert "FROM retirement_records" in response.sql
    assert "ORDER BY retirement_records.pension_amount DESC" in response.sql
    assert "LIMIT 1" in response.sql
