import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_employee_national_id_can_be_requested_by_name_and_position():
    response = await query_pipeline.execute(
        PipelineRequest(
            question="کد ملی کارمند نسرین هاشمی با شغل کارمند اداری",
            execute=False,
        )
    )

    assert response.intent["requested_entity"] == "employee"
    assert response.intent["first_name"] == "نسرین"
    assert response.intent["last_name"] == "هاشمی"
    assert response.intent["position"] == "کارمند اداری"
    assert response.intent["requested_columns"] == ["national_id"]
    assert response.sql is not None
    assert "employees.national_id" in response.sql
    assert "employees.first_name = 'نسرین'" in response.sql
    assert "employees.last_name = 'هاشمی'" in response.sql
    assert "employees.position = 'کارمند اداری'" in response.sql
    assert response.valid, response.errors

