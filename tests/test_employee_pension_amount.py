import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_employee_senavat_uses_pension_amount_column():
    response = await query_pipeline.execute(
        PipelineRequest(question='سنوات کارمند با کد ملی "2475429291"', execute=False)
    )

    assert response.group == "employee"
    assert response.valid is True
    assert response.intent["national_id"] == "2475429291"
    assert response.intent["wants_service_years"] is True
    assert "retirement_records.pension_amount" in response.sql
    assert "JOIN retirement_records ON retirement_records.employee_id = employees.id" in response.sql
    assert "employees.national_id = '2475429291'" in response.sql
