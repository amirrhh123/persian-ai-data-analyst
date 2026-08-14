import json

import pytest

from backend.execution.models import QueryResult
from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_pipeline_masks_sensitive_execution_result(monkeypatch):
    async def fake_answer(*args, **kwargs):
        class Answer:
            answer = "ok"
        return Answer()

    monkeypatch.setattr(
        "backend.pipeline.query_pipeline.execution_service.execute",
        lambda request: QueryResult(
            success=True,
            columns=["first_name", "national_id"],
            rows=[{"first_name": "Nasrin", "national_id": "8223876400"}],
            row_count=1,
        ),
    )
    monkeypatch.setattr(
        "backend.pipeline.query_pipeline.data_sensitivity_policy.sensitive_columns",
        lambda tenant_id=None: {("employees", "national_id"): "PII"},
    )
    monkeypatch.setattr(
        "backend.pipeline.query_pipeline.answer_service.generate_answer",
        fake_answer,
    )

    response = await query_pipeline.execute(
        PipelineRequest(question="اسم و فامیل کارمند با کد ملی 8223876400", execute=True)
    )

    assert response.result["rows"][0]["national_id"] == "***6400"
    assert response.result["data_policy"]["masked_columns"] == ["national_id"]
    explanation = json.loads(response.explanation)
    assert explanation["table_selection"]["tables"]
    assert explanation["result"]["data_policy"]["masked_columns"] == ["national_id"]
