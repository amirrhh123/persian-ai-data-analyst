from backend.pipeline.error_taxonomy import pipeline_error_taxonomy
from backend.pipeline.models import PipelineErrorDetail, PipelineResponse


def test_error_taxonomy_builds_structured_detail():
    detail = pipeline_error_taxonomy.detail(
        "sql.validation_failed",
        "sql_validation",
        "LIMIT too high",
    )

    assert isinstance(detail, PipelineErrorDetail)
    assert detail.code == "sql.validation_failed"
    assert detail.stage == "sql_validation"
    assert detail.user_message


def test_pipeline_response_supports_error_details():
    response = PipelineResponse(
        question="bad",
        success=False,
        errors=["bad sql"],
        error_details=[
            pipeline_error_taxonomy.detail("sql.validation_failed", "sql_validation", "bad sql")
        ],
    )

    assert response.error_details[0].code == "sql.validation_failed"


def test_error_taxonomy_endpoint():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    response = TestClient(app).get("/errors/taxonomy")

    assert response.status_code == 200
    codes = {item["code"] for item in response.json()["codes"]}
    assert "sql.validation_failed" in codes
    assert "execution.failed" in codes
