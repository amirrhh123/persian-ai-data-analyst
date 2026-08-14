from backend.pipeline.error_taxonomy import pipeline_error_taxonomy
from backend.pipeline.models import PipelineResponse


def test_lightweight_llm_disabled_error_code_is_documented():
    catalog = pipeline_error_taxonomy.catalog()
    codes = {item["code"]: item for item in catalog["codes"]}

    assert "sql.llm_disabled" in codes
    assert "حالت سبک" in codes["sql.llm_disabled"]["user_message"]


def test_pipeline_response_can_report_generation_source():
    response = PipelineResponse(
        question="یک سؤال خارج از الگو",
        success=False,
        valid=False,
        generation_source="llm_disabled",
    )

    assert response.generation_source == "llm_disabled"
