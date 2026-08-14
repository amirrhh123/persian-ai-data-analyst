import pytest

from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.pipeline.intent import QueryIntent, extract_intent
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline
from backend.sql.validator import SQLValidator


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=[
            TableInfo(
                name="students",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="first_name", data_type="character varying"),
                    ColumnInfo(name="school_id", data_type="integer"),
                ],
            ),
            TableInfo(
                name="schools",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="name", data_type="character varying"),
                ],
            ),
        ],
        relationships=[],
    )


def test_chandta_is_detected_as_count():
    intent = extract_intent("چندتا دانش آموز در مدرسه دبیرستان شهید بهشتی هستند؟")

    assert intent.requested_entity == "student"
    assert intent.aggregation == "COUNT"
    assert intent.named_school == "دبیرستان شهید بهشتی"


def test_validator_rejects_count_sql_for_explicit_list_request():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="student", wants_list=True)

    result = validator.validate(
        "SELECT COUNT(students.id) AS student_count FROM students",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("لیست" in error and "COUNT" in error for error in result.errors)


@pytest.mark.asyncio
async def test_student_count_by_school_uses_count_but_list_uses_rows():
    count_response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان مدرسه دبیرستان شهید بهشتی", execute=False)
    )
    list_response = await query_pipeline.execute(
        PipelineRequest(question="دانش آموزان مدرسه دبیرستان شهید بهشتی را نشان بده", execute=False)
    )

    assert count_response.valid is True
    assert count_response.intent["aggregation"] == "COUNT"
    assert "COUNT(students.id) AS student_count" in count_response.sql

    assert list_response.valid is True
    assert list_response.intent["aggregation"] is None
    assert list_response.intent["wants_list"] is True
    assert "COUNT(" not in list_response.sql
    assert "students.first_name" in list_response.sql
