import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_list_by_school_name_uses_students_schools_join():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="دانش آموزانی که در مدرسه دبیرستان فرزانگان مرودشت هستند",
            execute=False,
        )
    )

    assert response.group == "student"
    assert response.report == "student_list"
    assert response.valid is True
    assert response.intent["named_school"] == "دبیرستان فرزانگان مرودشت"
    assert "FROM students" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "schools.name = 'دبیرستان فرزانگان مرودشت'" in response.sql


@pytest.mark.asyncio
async def test_student_count_by_school_name_uses_count_template():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد دانش آموزان دبستان امید مرودشت را بگو",
            execute=False,
        )
    )

    assert response.group == "student"
    assert response.valid is True
    assert response.intent["named_school"] == "دبستان امید مرودشت"
    assert response.intent["aggregation"] == "COUNT"
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "JOIN schools ON students.school_id = schools.id" in response.sql
    assert "schools.name = 'دبستان امید مرودشت'" in response.sql


@pytest.mark.asyncio
async def test_school_name_containing_province_word_is_not_treated_as_province_filter():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد دانش آموزان مدرسه دبیرستان نمونه دولتی اصفهان",
            execute=False,
        )
    )

    assert response.group == "student"
    assert response.valid is True
    assert response.intent["named_school"] == "دبیرستان نمونه دولتی اصفهان"
    assert response.intent["province"] is None
    assert "schools.name = 'دبیرستان نمونه دولتی اصفهان'" in response.sql
    assert "organization_units.province = 'اصفهان'" not in response.sql
