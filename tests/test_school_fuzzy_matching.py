import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline
from backend.pipeline.school_resolver import resolve_school_name


def test_school_resolver_expands_partial_school_name():
    resolution = resolve_school_name("شهید بهشتی")

    assert resolution.resolved_name == "دبیرستان شهید بهشتی"
    assert resolution.ambiguous is False


def test_school_fragment_is_extracted_for_phone_question():
    intent = extract_intent("شماره تلفن شهید بهشتی")

    assert intent.requested_entity == "school"
    assert intent.wants_phone is True
    assert intent.named_school == "شهید بهشتی"


@pytest.mark.asyncio
async def test_school_phone_partial_name_resolves_to_exact_school():
    response = await query_pipeline.execute(
        PipelineRequest(question="شماره تلفن شهید بهشتی", execute=False)
    )

    assert response.valid is True
    assert response.intent["named_school"] == "دبیرستان شهید بهشتی"
    assert "schools.phone" in response.sql
    assert "schools.name = 'دبیرستان شهید بهشتی'" in response.sql


@pytest.mark.asyncio
async def test_students_by_partial_school_name_resolves_to_exact_school():
    response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزان مدرسه فرزانگان مرودشت را نشان بده", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["named_school"] == "دبیرستان فرزانگان مرودشت"
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "schools.name = 'دبیرستان فرزانگان مرودشت'" in response.sql


@pytest.mark.asyncio
async def test_student_count_by_partial_school_name_resolves_to_exact_school():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان امید مرودشت", execute=False)
    )

    assert response.valid is True
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["named_school"] == "دبستان امید مرودشت"
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "schools.name = 'دبستان امید مرودشت'" in response.sql
