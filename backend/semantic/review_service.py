import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.models import (
    SemanticReviewRequest,
    SemanticReviewResponse,
    SemanticSuggestionSet,
    normalize_identifier,
)


class SemanticReviewService:
    def __init__(self):
        self.settings = get_settings()

    def apply_review(
        self,
        request: SemanticReviewRequest,
        tenant_id: Optional[str] = None,
    ) -> SemanticReviewResponse:
        tenant = tenant_id or self.settings.tenant_id
        suggestions = semantic_activation_service.load_suggestions(tenant)
        path = semantic_activation_service.suggestions_path(tenant)

        canonical_table = self._resolve_table_name(suggestions, request.table)
        if request.target_type == "table":
            self._apply_table_review(suggestions, request, canonical_table)
        elif request.target_type == "column":
            self._apply_column_review(suggestions, request, canonical_table)
        else:
            return SemanticReviewResponse(
                status="not_found",
                tenant_id=tenant,
                target_type=request.target_type,
                table=request.table,
                column=request.column,
                message="target_type must be 'table' or 'column'.",
            )

        suggestions.status = "reviewed"
        self._save(suggestions, path)
        activation = semantic_activation_service.activate(tenant)
        activation_message = (
            f" Activation status: {activation.status}."
            if activation.status != "blocked"
            else " Activation was blocked; run database health check and fix validation errors."
        )
        return SemanticReviewResponse(
            status="success",
            tenant_id=tenant,
            target_type=request.target_type,
            table=canonical_table,
            column=request.column,
            output_path=str(path),
            message="Semantic review was applied to suggestions and activation was attempted." + activation_message,
        )

    def _resolve_table_name(self, suggestions: SemanticSuggestionSet, table_name: str) -> str:
        normalized = normalize_identifier(table_name)
        table = next((item for item in suggestions.tables if normalize_identifier(item.name) == normalized), None)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found in semantic suggestions.")
        return table.name

    def _apply_table_review(
        self,
        suggestions: SemanticSuggestionSet,
        request: SemanticReviewRequest,
        canonical_table: str,
    ) -> None:
        table = next((item for item in suggestions.tables if item.name == canonical_table), None)
        if table is None:
            raise ValueError(f"Table '{request.table}' not found in semantic suggestions.")
        if request.entity is not None:
            table.entity = request.entity
        if request.display_name_fa is not None:
            table.display_name_fa = request.display_name_fa
        if request.description_fa is not None:
            table.description_fa = request.description_fa
        if request.aliases_fa is not None:
            table.aliases_fa = request.aliases_fa
        if request.approved:
            table.review_required = False
            table.confidence = max(table.confidence, 0.9)
            self._add_reason(table.confidence_reasons, "human_review_approved")

    def _apply_column_review(
        self,
        suggestions: SemanticSuggestionSet,
        request: SemanticReviewRequest,
        canonical_table: str,
    ) -> None:
        if not request.column:
            raise ValueError("column is required for column review.")
        table = next((item for item in suggestions.tables if item.name == canonical_table), None)
        if table is None:
            raise ValueError(f"Table '{request.table}' not found in semantic suggestions.")
        column = next((item for item in table.columns if normalize_identifier(item.name) == normalize_identifier(request.column)), None)
        if column is None:
            raise ValueError(f"Column '{request.table}.{request.column}' not found in semantic suggestions.")
        if request.display_name_fa is not None:
            column.display_name_fa = request.display_name_fa
        if request.description_fa is not None:
            column.description_fa = request.description_fa
        if request.aliases_fa is not None:
            column.aliases_fa = request.aliases_fa
        if request.value_type is not None:
            column.value_type = request.value_type
        if request.pii is not None:
            column.pii = request.pii
        if request.approved:
            column.confidence = max(column.confidence, 0.9)
            self._add_reason(column.confidence_reasons, "human_review_approved")
            if all(item.confidence >= 0.55 for item in table.columns):
                table.review_required = False

    def _save(self, suggestions: SemanticSuggestionSet, path: Path) -> None:
        payload = suggestions.model_dump(mode="json")
        payload["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _add_reason(self, reasons: list[str], reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)


semantic_review_service = SemanticReviewService()
