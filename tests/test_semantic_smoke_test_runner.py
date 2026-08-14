import json

import pytest

from backend.pipeline.models import PipelineResponse
from backend.semantic.models import SemanticSmokeTestCase
from backend.semantic.smoke_test_runner import SemanticSmokeTestRunner


def _case() -> SemanticSmokeTestCase:
    return SemanticSmokeTestCase(
        id="smoke_training_requests_count",
        table="training_requests",
        kind="count",
        question="تعداد رکوردهای جدول training requests را بگو",
        expected={
            "aggregation": "COUNT",
            "sql_contains": ["FROM training_requests", "COUNT("],
        },
    )


@pytest.mark.asyncio
async def test_smoke_test_runner_passes_matching_pipeline_response(monkeypatch):
    runner = SemanticSmokeTestRunner()

    async def fake_execute(request):
        return PipelineResponse(
            question=request.question,
            success=True,
            valid=True,
            sql="SELECT COUNT(*) AS row_count FROM training_requests",
            intent={"aggregation": "COUNT"},
        )

    monkeypatch.setattr("backend.semantic.smoke_test_runner.query_pipeline.execute", fake_execute)

    result = await runner._run_case(_case())

    assert result.passed is True
    assert result.failures == []
    assert result.failure_stage == ""


@pytest.mark.asyncio
async def test_smoke_test_runner_classifies_validation_failure(monkeypatch):
    runner = SemanticSmokeTestRunner()

    async def fake_execute(request):
        return PipelineResponse(
            question=request.question,
            success=False,
            valid=False,
            sql="",
            errors=["invalid sql"],
        )

    monkeypatch.setattr("backend.semantic.smoke_test_runner.query_pipeline.execute", fake_execute)

    result = await runner._run_case(_case())

    assert result.passed is False
    assert result.error_code == "sql.validation_failed"
    assert result.failure_stage == "validation"


@pytest.mark.asyncio
async def test_smoke_test_runner_runs_cases_from_file_and_saves(monkeypatch, tmp_path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([_case().model_dump(mode="json")], ensure_ascii=False), encoding="utf-8")
    runner = SemanticSmokeTestRunner()

    async def fake_execute(request):
        return PipelineResponse(
            question=request.question,
            success=True,
            valid=True,
            sql="SELECT COUNT(*) AS row_count FROM training_requests",
            intent={"aggregation": "COUNT"},
        )

    monkeypatch.setattr("backend.semantic.smoke_test_runner.query_pipeline.execute", fake_execute)
    monkeypatch.setattr(runner, "save_response", lambda response: (tmp_path / "out.json", tmp_path / "latest.json"))

    response = await runner.run("demo", cases_path=cases_path)

    assert response.status == "passed"
    assert response.summary.total == 1
    assert response.summary.passed == 1
    assert response.output_path == str(tmp_path / "out.json")


def test_smoke_test_runner_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from backend.semantic.models import SemanticSmokeTestRunResponse, SemanticSmokeTestRunSummary
    from fastapi.testclient import TestClient

    async def fake_run(*args, **kwargs):
        return SemanticSmokeTestRunResponse(
            status="passed",
            tenant_id="education_ministry",
            summary=SemanticSmokeTestRunSummary(total=1, passed=1, failed=0, pass_rate=100),
            results=[],
        )

    monkeypatch.setattr(main.semantic_smoke_test_runner, "run", fake_run)

    response = TestClient(app).post("/semantic/smoke-tests/run")

    assert response.status_code == 200
    assert response.json()["status"] == "passed"


def test_smoke_test_runner_summarizes_lightweight_readiness():
    from backend.semantic.models import SemanticSmokeTestResult

    runner = SemanticSmokeTestRunner()
    summary = runner._summarize(
        [
            SemanticSmokeTestResult(
                id="template_ok",
                table="demo",
                kind="count",
                question="q1",
                passed=True,
                response={"generation_source": "template"},
            ),
            SemanticSmokeTestResult(
                id="llm_ok",
                table="demo",
                kind="list",
                question="q2",
                passed=True,
                response={"generation_source": "llm"},
            ),
            SemanticSmokeTestResult(
                id="needs_llm",
                table="demo",
                kind="complex",
                question="q3",
                passed=False,
                error_code="sql.llm_disabled",
                response={"generation_source": "llm_disabled"},
            ),
        ]
    )

    assert summary.total == 3
    assert summary.deterministic_sql == 1
    assert summary.llm_sql == 1
    assert summary.llm_required == 1
    assert summary.lightweight_ready == 1
    assert summary.lightweight_ready_rate == 33.33


def test_lightweight_readiness_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from backend.semantic.models import SemanticSmokeTestRunResponse, SemanticSmokeTestRunSummary
    from fastapi.testclient import TestClient

    async def fake_run(*args, **kwargs):
        assert kwargs["execute"] is False
        assert kwargs["save"] is False
        return SemanticSmokeTestRunResponse(
            status="passed",
            tenant_id="education_ministry",
            summary=SemanticSmokeTestRunSummary(
                total=2,
                passed=2,
                failed=0,
                pass_rate=100,
                lightweight_ready=2,
                lightweight_ready_rate=100,
            ),
            results=[],
        )

    monkeypatch.setattr(main.semantic_smoke_test_runner, "run", fake_run)

    response = TestClient(app).get("/semantic/lightweight-readiness?limit=2")

    assert response.status_code == 200
    assert response.json()["summary"]["lightweight_ready_rate"] == 100
