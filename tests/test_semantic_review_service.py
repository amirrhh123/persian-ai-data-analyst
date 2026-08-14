import json

from backend.semantic.models import (
    SemanticActivationResponse,
    SemanticColumnSuggestion,
    SemanticReviewRequest,
    SemanticSuggestionSet,
    SemanticTableSuggestion,
)
from backend.semantic.review_service import SemanticReviewService


def _suggestions() -> SemanticSuggestionSet:
    return SemanticSuggestionSet(
        tenant_id="demo",
        source_fingerprint="abc",
        generated_at="2026-07-26T10:00:00",
        tables=[
            SemanticTableSuggestion(
                name="training_requests",
                entity="training_requests",
                display_name_fa="training requests",
                description_fa="unknown",
                aliases_fa=["training requests"],
                confidence=0.4,
                review_required=True,
                columns=[
                    SemanticColumnSuggestion(
                        name="requester_role",
                        data_type="character varying",
                        display_name_fa="requester role",
                        description_fa="unknown",
                        aliases_fa=["requester role"],
                        confidence=0.4,
                    )
                ],
            )
        ],
    )


def test_semantic_review_approves_table(monkeypatch, tmp_path):
    path = tmp_path / "semantic_suggestions.json"
    suggestions = _suggestions()
    path.write_text(suggestions.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.load_suggestions",
        lambda tenant_id: SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8"))),
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: path,
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.activate",
        lambda tenant_id: SemanticActivationResponse(status="activated", tenant_id=tenant_id),
    )

    response = SemanticReviewService().apply_review(
        SemanticReviewRequest(
            target_type="table",
            table="training_requests",
            display_name_fa="درخواست‌های آموزشی",
            aliases_fa=["درخواست آموزشی"],
            entity="training_request",
        ),
        tenant_id="demo",
    )

    updated = SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8")))
    table = updated.tables[0]
    assert response.status == "success"
    assert table.review_required is False
    assert table.confidence >= 0.9
    assert table.entity == "training_request"
    assert table.aliases_fa == ["درخواست آموزشی"]
    assert "human_review_approved" in table.confidence_reasons
    assert "activation was attempted" in response.message


def test_semantic_review_approves_column(monkeypatch, tmp_path):
    path = tmp_path / "semantic_suggestions.json"
    path.write_text(_suggestions().model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.load_suggestions",
        lambda tenant_id: SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8"))),
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: path,
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.activate",
        lambda tenant_id: SemanticActivationResponse(status="activated", tenant_id=tenant_id),
    )

    SemanticReviewService().apply_review(
        SemanticReviewRequest(
            target_type="column",
            table="training_requests",
            column="requester_role",
            display_name_fa="پست درخواست‌دهنده",
            aliases_fa=["پست", "سمت"],
            value_type="category",
        ),
        tenant_id="demo",
    )

    column = SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8"))).tables[0].columns[0]
    assert column.confidence >= 0.9
    assert column.display_name_fa == "پست درخواست‌دهنده"
    assert column.aliases_fa == ["پست", "سمت"]
    assert column.value_type == "category"


def test_semantic_review_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from backend.semantic.models import SemanticReviewResponse
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        main.semantic_review_service,
        "apply_review",
        lambda request, tenant_id=None: SemanticReviewResponse(
            status="success",
            tenant_id="education_ministry",
            target_type=request.target_type,
            table=request.table,
            column=request.column,
        ),
    )

    response = TestClient(app).post(
        "/semantic/review",
        json={"target_type": "table", "table": "training_requests", "aliases_fa": ["درخواست"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_semantic_review_normalizes_persian_digits_in_table_and_column_names(monkeypatch, tmp_path):
    path = tmp_path / "semantic_suggestions.json"
    suggestions = SemanticSuggestionSet(
        tenant_id="demo",
        source_fingerprint="abc",
        generated_at="2026-07-26T10:00:00",
        tables=[
            SemanticTableSuggestion(
                name="test1",
                entity="test1",
                display_name_fa="test1",
                description_fa="unknown",
                aliases_fa=["test1"],
                confidence=0.4,
                review_required=True,
                columns=[
                    SemanticColumnSuggestion(
                        name="col1",
                        data_type="integer",
                        display_name_fa="col1",
                        description_fa="unknown",
                        aliases_fa=["col1"],
                        confidence=0.4,
                    )
                ],
            )
        ],
    )
    path.write_text(suggestions.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.load_suggestions",
        lambda tenant_id: SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8"))),
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.suggestions_path",
        lambda tenant_id: path,
    )
    monkeypatch.setattr(
        "backend.semantic.review_service.semantic_activation_service.activate",
        lambda tenant_id: SemanticActivationResponse(status="activated", tenant_id=tenant_id),
    )

    response = SemanticReviewService().apply_review(
        SemanticReviewRequest(
            target_type="column",
            table="test\u06f1",
            column="col\u06f1",
            aliases_fa=["\u0633\u062a\u0648\u0646 \u062a\u0633\u062a"],
        ),
        tenant_id="demo",
    )

    updated = SemanticSuggestionSet.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert response.table == "test1"
    assert updated.tables[0].columns[0].aliases_fa == ["\u0633\u062a\u0648\u0646 \u062a\u0633\u062a"]
