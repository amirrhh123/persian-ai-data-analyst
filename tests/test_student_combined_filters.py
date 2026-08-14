import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_status_grade_and_province_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزان فعال پایه دهم استان تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["status"] == "active"
    assert response.intent["grade"] == "دهم"
    assert response.intent["province"] == "تهران"
    assert "organization_units.province = 'تهران'" in response.sql
    assert "students.status = 'active'" in response.sql
    assert "students.grade = 'دهم'" in response.sql


@pytest.mark.asyncio
async def test_student_count_city_grade_and_last_name_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان پایه دوازدهم شهر شیراز که فامیلشان محمدی است", execute=False)
    )

    assert response.valid is True
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["city"] == "شیراز"
    assert response.intent["grade"] == "دوازدهم"
    assert response.intent["last_name"] == "محمدی"
    assert "organization_units.city = 'شیراز'" in response.sql
    assert "students.grade = 'دوازدهم'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "COUNT(students.id) AS student_count" in response.sql


@pytest.mark.asyncio
async def test_student_enrollment_year_and_province_filters_are_combined():
    response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزان سال ثبت نام ۱۴۰۲ استان تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["enrollment_year"] == 1402
    assert response.intent["province"] == "تهران"
    assert "organization_units.province = 'تهران'" in response.sql
    assert "students.enrollment_year = 1402" in response.sql


@pytest.mark.asyncio
async def test_student_total_count_can_filter_by_grade_and_enrollment_year():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان پایه دهم سال ثبت نام ۱۴۰۲", execute=False)
    )

    assert response.valid is True
    assert response.intent["aggregation"] == "COUNT"
    assert response.intent["grade"] == "دهم"
    assert response.intent["enrollment_year"] == 1402
    assert "COUNT(students.id) AS total_students" in response.sql
    assert "students.grade = 'دهم'" in response.sql
    assert "students.enrollment_year = 1402" in response.sql
