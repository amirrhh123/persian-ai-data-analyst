import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline
from backend.pipeline.safety.multi_intent_detector import multi_intent_detector


def test_school_student_counts_by_province_are_composable():
    detection = multi_intent_detector.detect("تعداد مدارس و دانش آموزان هر استان")

    assert detection["multi_intent"] is True
    assert detection["is_composable"] is True
    assert detection["shared_grouping_dimension"] == "province"
    assert {"school", "student"}.issubset(set(detection["detected_entities"]))


@pytest.mark.asyncio
async def test_school_student_counts_by_province_uses_school_and_student_counts():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس و دانش آموزان هر استان", execute=False)
    )

    assert response.valid is True
    assert "COUNT(DISTINCT sc.id)" in response.sql
    assert "AS school_count" in response.sql
    assert "COUNT(st.id)" in response.sql
    assert "AS student_count" in response.sql
    assert "employee_count" not in response.sql
    assert "GROUP BY ou.province" in response.sql


@pytest.mark.asyncio
async def test_school_student_counts_for_specific_province_are_composable():
    response = await query_pipeline.execute(
        PipelineRequest(question="در تهران چند مدرسه و چند دانش آموز داریم؟", execute=False)
    )

    assert response.valid is True
    assert "AS school_count" in response.sql
    assert "AS student_count" in response.sql
    assert "WHERE ou.province = 'تهران'" in response.sql


@pytest.mark.asyncio
async def test_employee_student_counts_by_province_still_use_employee_count():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارکنان و دانش آموزان هر استان", execute=False)
    )

    assert response.valid is True
    assert "AS employee_count" in response.sql
    assert "AS student_count" in response.sql
    assert "AS school_count" not in response.sql
