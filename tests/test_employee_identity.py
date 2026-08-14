import pytest


@pytest.mark.asyncio
async def test_employee_identity_by_national_id_quotes_text_identifier():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    question = (
        "\u0627\u0633\u0645 \u0648 \u0641\u0627\u0645\u06cc\u0644 "
        "\u06a9\u0627\u0631\u0645\u0646\u062f \u0628\u0627 "
        "\u06a9\u062f \u0645\u0644\u06cc 8223876400"
    )
    response = await query_pipeline.execute(PipelineRequest(question=question, execute=False))

    assert response.group == "employee"
    assert response.report == "employee_list"
    assert response.valid is True
    assert response.intent["national_id"] == "8223876400"
    assert "employees.first_name" in response.sql
    assert "employees.last_name" in response.sql
    assert "employees.national_id" in response.sql
    assert "employees.national_id = '8223876400'" in response.sql


@pytest.mark.asyncio
async def test_employee_full_profile_by_national_id_executes():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    question = (
        "\u06a9\u0627\u0631\u0645\u0646\u062f \u0628\u0627 "
        "\u06a9\u062f \u0645\u0644\u06cc 4871587050 "
        "\u0648\u0636\u0639\u06cc\u062a \u0648 \u0634\u063a\u0644 "
        "\u0648 \u0627\u0633\u0645 \u0648 \u0641\u0627\u0645\u06cc\u0644 "
        "\u0648 \u062a\u0645\u0627\u0645 \u0633\u062a\u0648\u0646 \u0647\u0627"
    )
    response = await query_pipeline.execute(PipelineRequest(question=question, execute=True))

    assert response.success is True
    assert response.valid is True
    assert response.intent["national_id"] == "4871587050"
    assert "employees.position" in response.sql
    assert "employees.status" in response.sql
    assert "employees.organization_unit_id" in response.sql
    assert "employees.hire_date" in response.sql
    assert "employees.created_at" in response.sql
    rows = response.result["rows"]
    assert len(rows) == 1
    assert rows[0]["national_id"] == "4871587050"
    assert {"first_name", "last_name", "position", "status"}.issubset(rows[0].keys())
