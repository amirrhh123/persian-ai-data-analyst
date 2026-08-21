import pytest

from backend.pipeline.intent import extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


def test_student_last_name_filter_is_extracted():
    intent = extract_intent("دانش آموزانی که فامیلشان محمدی است")

    assert intent.requested_entity == "student"
    assert intent.last_name == "محمدی"
    assert intent.first_name is None


def test_employee_full_name_filter_is_extracted():
    intent = extract_intent("کارمند علی احمدی را نشان بده")

    assert intent.requested_entity == "employee"
    assert intent.first_name == "علی"
    assert intent.last_name == "احمدی"
    assert intent.named_employee == "علی احمدی"


def test_student_count_with_by_name_extracts_both_name_parts():
    intent = extract_intent("تعداد دانش آموز با نام امید خسروی")

    assert intent.requested_entity == "student"
    assert intent.aggregation == "COUNT"
    assert intent.first_name == "امید"
    assert intent.last_name == "خسروی"


@pytest.mark.asyncio
async def test_student_count_by_full_name_keeps_filters_in_final_sql():
    from backend.pipeline.query_pipeline import PipelineRequest, query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(
            question="تعداد دانش آموز با نام امید خسروی",
            execute=False,
        )
    )

    assert response.success is True
    assert response.valid is True
    assert response.sql is not None
    assert "COUNT(" in response.sql.upper()
    assert "first_name" in response.sql
    assert "last_name" in response.sql
    assert "امید" in response.sql
    assert "خسروی" in response.sql


@pytest.mark.asyncio
async def test_ranking_type_by_employee_full_name_uses_join_and_name_filters():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="نوع رتبه بندی کارمند با نام امیر احمدی",
            execute=False,
        )
    )

    assert response.success is True
    assert response.valid is True
    assert response.sql is not None
    assert "ranking_requests.ranking_type" in response.sql
    assert "JOIN employees ON ranking_requests.employee_id = employees.id" in response.sql
    assert "employees.first_name = 'امیر'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql
    assert "employees.status" not in response.sql
    assert "`" not in response.sql


@pytest.mark.asyncio
async def test_student_last_name_list_uses_last_name_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزانی که فامیلشان محمدی است", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "student"
    assert response.intent["last_name"] == "محمدی"
    assert "FROM students" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "COUNT(" not in response.sql


@pytest.mark.asyncio
async def test_student_full_name_count_by_province_uses_both_names():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان استان تهران که اسمشان پوریا و فامیلشان محمدی است", execute=False)
    )

    assert response.valid is True
    assert response.intent["first_name"] == "پوریا"
    assert response.intent["last_name"] == "محمدی"
    assert "organization_units.province = 'تهران'" in response.sql
    assert "students.first_name = 'پوریا'" in response.sql
    assert "students.last_name = 'محمدی'" in response.sql
    assert "COUNT(students.id) AS student_count" in response.sql


@pytest.mark.asyncio
async def test_employee_full_name_list_uses_both_names():
    response = await query_pipeline.execute(
        PipelineRequest(question="کارمند علی احمدی را نشان بده", execute=False)
    )

    assert response.valid is True
    assert response.intent["requested_entity"] == "employee"
    assert response.intent["first_name"] == "علی"
    assert response.intent["last_name"] == "احمدی"
    assert "FROM employees" in response.sql
    assert "employees.first_name = 'علی'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql


@pytest.mark.asyncio
async def test_employee_last_name_by_city_keeps_location_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات کارمندان شهر تهران که نام خانوادگی احمدی دارند", execute=False)
    )

    assert response.valid is True
    assert response.intent["last_name"] == "احمدی"
    assert "organization_units.city = 'تهران'" in response.sql
    assert "employees.last_name = 'احمدی'" in response.sql
