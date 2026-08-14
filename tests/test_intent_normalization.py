import pytest

from backend.pipeline.intent import extract_intent, normalize_intent
from backend.pipeline.models import PipelineResponse


def test_normalized_intent_count_student_by_province():
    intent = extract_intent("تعداد دانش آموزان استان تهران")
    normalized = normalize_intent(intent)

    assert normalized.entity == "student"
    assert normalized.operation == "count"
    assert {"entity_detected", "operation_detected", "filters_detected"}.issubset(set(normalized.reasons))
    assert any(item.field == "province" and item.value == "تهران" for item in normalized.filters)
    assert normalized.metrics == ["*"]
    assert normalized.confidence >= 0.75


def test_normalized_intent_employee_profile_by_national_id():
    intent = extract_intent("اطلاعات کامل کارمند با کد ملی 4871587050")
    normalized = normalize_intent(intent)

    assert normalized.entity == "employee"
    assert normalized.operation == "profile"
    assert any(item.field == "national_id" and item.value == "4871587050" for item in normalized.filters)
    assert normalized.confidence >= 0.75


def test_normalized_intent_grouped_count_has_dimension():
    intent = extract_intent("تعداد مدارس به تفکیک استان")
    normalized = normalize_intent(intent)

    assert normalized.entity == "school"
    assert normalized.operation == "count"
    assert "province" in normalized.dimensions


def test_information_student_broad_filters_normalizes_as_list():
    intent = extract_intent("\u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062f\u0627\u0646\u0634 \u0622\u0645\u0648\u0632\u0627\u0646 \u0627\u0633\u062a\u0627\u0646 \u062a\u0647\u0631\u0627\u0646 \u067e\u0627\u06cc\u0647 \u06cc\u0627\u0632\u062f\u0647\u0645")
    normalized = normalize_intent(intent)

    assert intent.wants_full_profile is True
    assert normalized.entity == "student"
    assert normalized.operation == "list"
    assert any(item.field == "province" for item in normalized.filters)
    assert any(item.field == "grade" for item in normalized.filters)


def test_information_student_partial_name_filter_normalizes_as_list():
    intent = extract_intent("\u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062f\u0627\u0646\u0634 \u0622\u0645\u0648\u0632\u0627\u0646 \u0627\u0633\u062a\u0627\u0646 \u062a\u0647\u0631\u0627\u0646 \u0628\u0627 \u0646\u0627\u0645 \u067e\u0648\u0631\u06cc\u0627")
    normalized = normalize_intent(intent)

    assert intent.wants_full_profile is True
    assert normalized.entity == "student"
    assert normalized.operation == "list"
    assert any(item.field == "province" for item in normalized.filters)
    assert any(item.field == "first_name" for item in normalized.filters)


@pytest.mark.asyncio
async def test_pipeline_response_can_include_normalized_intent(monkeypatch):
    from backend.pipeline.query_pipeline import QueryPipeline
    from backend.pipeline.models import PipelineRequest

    pipeline = QueryPipeline()

    async def fake_execute(request):
        intent = extract_intent(request.question)
        payload = intent.model_dump()
        payload["normalized"] = normalize_intent(intent).model_dump()
        return PipelineResponse(
            question=request.question,
            success=True,
            valid=True,
            intent=payload,
            sql="SELECT 1",
        )

    monkeypatch.setattr(pipeline, "execute", fake_execute)

    response = await pipeline.execute(PipelineRequest(question="تعداد دانش آموزان استان تهران", execute=False))

    assert response.intent["normalized"]["entity"] == "student"
    assert response.intent["normalized"]["operation"] == "count"
