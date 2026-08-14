import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_student_identity_by_quoted_national_id():
    response = await query_pipeline.execute(
        PipelineRequest(question='نام دانش آموز با کد ملی "3489881390"', execute=False)
    )

    assert response.group == "student"
    assert response.report == "student_list"
    assert response.valid is True
    assert response.intent["national_id"] == "3489881390"
    assert response.intent["named_student"] is None
    assert "FROM students" in response.sql
    assert "students.national_id = '3489881390'" in response.sql
    assert "students.national_id = 3489881390" not in response.sql
