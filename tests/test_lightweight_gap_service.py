import pytest

from backend.semantic.lightweight_gap_service import LightweightGapService
from backend.semantic.models import (
    SemanticSmokeTestResult,
    SemanticSmokeTestRunResponse,
    SemanticSmokeTestRunSummary,
)


@pytest.mark.asyncio
async def test_lightweight_gap_service_suggests_actions_for_llm_disabled_cases(monkeypatch):
    service = LightweightGapService()

    async def fake_run(*args, **kwargs):
        return SemanticSmokeTestRunResponse(
            status="failed",
            tenant_id="education_ministry",
            summary=SemanticSmokeTestRunSummary(
                total=2,
                passed=1,
                failed=1,
                pass_rate=50,
                lightweight_ready=1,
                lightweight_ready_rate=50,
                llm_required=1,
            ),
            results=[
                SemanticSmokeTestResult(
                    id="ok",
                    table="demo_training_requests",
                    kind="count",
                    question="تعداد درخواست‌ها",
                    passed=True,
                    response={"generation_source": "template"},
                ),
                SemanticSmokeTestResult(
                    id="gap",
                    table="demo_training_requests",
                    kind="group_by",
                    question="تعداد درخواست‌ها به تفکیک پست",
                    passed=False,
                    error_code="sql.llm_disabled",
                    response={"generation_source": "llm_disabled"},
                ),
            ],
        )

    monkeypatch.setattr("backend.semantic.lightweight_gap_service.semantic_smoke_test_runner.run", fake_run)

    response = await service.suggest("education_ministry", limit=2)

    assert response.status == "needs_semantic_work"
    assert response.gap_count == 1
    assert response.lightweight_ready_rate == 50
    assert response.suggestions[0].table == "demo_training_requests"
    assert "template" in response.suggestions[0].technical_hint
    assert "اصلاح معنی" in response.suggestions[0].admin_hint
    payload = response.suggestions[0].suggested_review_payload
    assert payload["target_type"] == "table"
    assert payload["table"] == "demo_training_requests"
    assert payload["approved"] is True
    assert payload["aliases_fa"]


def test_lightweight_gap_suggestions_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from backend.semantic.models import LightweightGapSuggestionResponse
    from fastapi.testclient import TestClient

    async def fake_suggest(*args, **kwargs):
        return LightweightGapSuggestionResponse(
            status="ready",
            tenant_id="education_ministry",
            total_cases=1,
            lightweight_ready_rate=100,
            gap_count=0,
            suggestions=[],
        )

    monkeypatch.setattr(main.lightweight_gap_service, "suggest", fake_suggest)

    response = TestClient(app).get("/semantic/lightweight-gap-suggestions?limit=1")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_lightweight_gap_service_applies_suggested_review_payloads(monkeypatch):
    from backend.semantic.models import LightweightGapSuggestion, LightweightGapSuggestionResponse, SemanticReviewResponse

    service = LightweightGapService()

    async def fake_suggest(*args, **kwargs):
        return LightweightGapSuggestionResponse(
            status="needs_semantic_work",
            tenant_id="education_ministry",
            gap_count=1,
            suggestions=[
                LightweightGapSuggestion(
                    question="تعداد درخواست‌ها به تفکیک پست",
                    table="demo_training_requests",
                    kind="group_by",
                    error_code="sql.llm_disabled",
                    recommended_action="review",
                    admin_hint="hint",
                    suggested_review_payload={
                        "target_type": "table",
                        "table": "demo_training_requests",
                        "column": None,
                        "aliases_fa": ["درخواست‌ها"],
                        "display_name_fa": "درخواست‌ها",
                        "approved": True,
                        "note": "operator-only note",
                    },
                )
            ],
        )

    def fake_apply_review(request, tenant_id):
        assert tenant_id == "education_ministry"
        assert request.table == "demo_training_requests"
        assert request.aliases_fa == ["درخواست‌ها"]
        assert not hasattr(request, "note")
        return SemanticReviewResponse(
            status="success",
            tenant_id=tenant_id,
            target_type=request.target_type,
            table=request.table,
            column=request.column,
            message="ok",
        )

    def fake_validate_current(tenant_id):
        from backend.semantic.models import SemanticActivationResponse, SemanticValidationIssue

        return SemanticActivationResponse(
            status="valid",
            tenant_id=tenant_id,
            issues=[
                SemanticValidationIssue(
                    severity="warning",
                    code="review_required",
                    message="one low-confidence item remains",
                )
            ],
        )

    monkeypatch.setattr(service, "suggest", fake_suggest)
    monkeypatch.setattr("backend.semantic.lightweight_gap_service.semantic_review_service.apply_review", fake_apply_review)
    monkeypatch.setattr("backend.semantic.lightweight_gap_service.semantic_activation_service.validate_current", fake_validate_current)

    response = await service.apply_suggestions("education_ministry", limit=1)

    assert response.status == "applied_validated"
    assert response.requested == 1
    assert response.applied == 1
    assert response.failed == 0
    assert response.validation_status == "valid"
    assert response.validation_errors == 0
    assert response.validation_warnings == 1
    assert "به‌روزرسانی کامل سیستم" in response.next_action
    assert response.results[0].payload["table"] == "demo_training_requests"


def test_lightweight_gap_apply_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from backend.semantic.models import LightweightGapApplyResponse
    from fastapi.testclient import TestClient

    async def fake_apply(*args, **kwargs):
        assert kwargs["validate_after"] is False
        return LightweightGapApplyResponse(
            status="success",
            tenant_id="education_ministry",
            requested=1,
            applied=1,
            failed=0,
            results=[],
        )

    monkeypatch.setattr(main.lightweight_gap_service, "apply_suggestions", fake_apply)

    response = TestClient(app).post("/semantic/lightweight-gap-suggestions/apply?limit=1&validate_after=false")

    assert response.status_code == 200
    assert response.json()["applied"] == 1
