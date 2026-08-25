"""Persist feedback safely and derive bounded retrieval adjustments."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from backend.config import get_settings

from backend.feedback.models import (
    FeedbackEvent,
    FeedbackRequest,
    FeedbackResponse,
    FeedbackSummary,
)


class FeedbackService:
    """Local feedback store with exact-question relevance adjustments."""

    def __init__(self, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).parent.parent.parent / "schema"

    def path(self, tenant_id: str) -> Path:
        return self.schema_root / "tenants" / tenant_id / "feedback.json"

    @staticmethod
    def _normalize_question(question: str) -> str:
        return " ".join(question.casefold().replace("ي", "ی").replace("ك", "ک").split())

    def fingerprint(self, question: str) -> str:
        return hashlib.sha256(self._normalize_question(question).encode("utf-8")).hexdigest()

    @staticmethod
    def redact_question(question: str) -> str:
        if not get_settings().data_masking_enabled:
            return question
        redacted = re.sub(r"\b[0-9۰-۹]{10}\b", "***", question)
        redacted = re.sub(r"'(?:''|[^'])*'", "'***'", redacted)
        return redacted

    def load(self, tenant_id: str) -> list[FeedbackEvent]:
        path = self.path(tenant_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return [FeedbackEvent.model_validate(item) for item in payload]

    def _save(self, tenant_id: str, events: list[FeedbackEvent]) -> None:
        path = self.path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                [event.model_dump(mode="json") for event in events],
                file,
                ensure_ascii=False,
                indent=2,
            )
        temporary.replace(path)

    def submit(self, tenant_id: str, request: FeedbackRequest) -> FeedbackResponse:
        """Insert or replace one user's feedback for a query response."""
        events = self.load(tenant_id)
        event = FeedbackEvent(
            id=str(uuid4()),
            query_id=request.query_id,
            tenant_id=tenant_id,
            created_at=datetime.now(),
            question_fingerprint=self.fingerprint(request.question),
            question_redacted=self.redact_question(request.question),
            rating=request.rating,
            selected_group=request.selected_group,
            selected_report=request.selected_report,
            corrected_group=request.corrected_group,
            corrected_report=request.corrected_report,
            served_table=request.served_table,
            corrected_table=request.corrected_table,
            comment=request.comment.strip() if request.comment else None,
        )
        events = [item for item in events if item.query_id != request.query_id]
        events.append(event)
        self._save(tenant_id, events)
        return FeedbackResponse(
            status="saved",
            feedback_id=event.id,
            message="Feedback was saved and will influence only bounded retrieval ranking.",
        )

    def candidate_adjustments(
        self,
        tenant_id: str,
        question: str,
        target_type: str,
    ) -> dict[str, float]:
        """Return bounded boosts/penalties for the exact normalized question."""
        if target_type not in {"group", "report"}:
            raise ValueError("target_type must be group or report")
        fingerprint = self.fingerprint(question)
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        selected_field = f"selected_{target_type}"
        corrected_field = f"corrected_{target_type}"
        for event in self.load(tenant_id):
            if event.question_fingerprint != fingerprint:
                continue
            selected = getattr(event, selected_field)
            corrected = getattr(event, corrected_field)
            if selected:
                totals[selected] = totals.get(selected, 0.0) + (
                    0.04 if event.rating == "positive" else -0.06
                )
                counts[selected] = counts.get(selected, 0) + 1
            if corrected and event.rating == "negative":
                totals[corrected] = totals.get(corrected, 0.0) + 0.08
                counts[corrected] = counts.get(corrected, 0) + 1
        return {
            candidate: round(max(-0.15, min(0.15, total / counts[candidate])), 4)
            for candidate, total in totals.items()
        }

    def table_adjustments(self, tenant_id: str, question: str) -> dict[str, float]:
        """Bounded per-question table boosts/penalties from grounding feedback.

        Same exact-question scope as candidate_adjustments: privacy-safe and
        deterministic. Negative ratings penalize the served table; a declared
        corrected table gets the boost. Positive ratings gently reinforce.
        """
        fingerprint = self.fingerprint(question)
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for event in self.load(tenant_id):
            if event.question_fingerprint != fingerprint:
                continue
            if event.served_table:
                delta = -0.08 if event.rating == "negative" else 0.03
                totals[event.served_table] = totals.get(event.served_table, 0.0) + delta
                counts[event.served_table] = counts.get(event.served_table, 0) + 1
            if event.corrected_table and event.rating == "negative":
                totals[event.corrected_table] = totals.get(event.corrected_table, 0.0) + 0.12
                counts[event.corrected_table] = counts.get(event.corrected_table, 0) + 1
        return {
            table: round(max(-0.20, min(0.20, total / counts[table])), 4)
            for table, total in totals.items()
        }

    def summary(self, tenant_id: str) -> FeedbackSummary:
        events = self.load(tenant_id)
        positive = sum(event.rating == "positive" for event in events)
        negative = len(events) - positive
        corrections = sum(bool(event.corrected_group or event.corrected_report) for event in events)
        return FeedbackSummary(
            tenant_id=tenant_id,
            total=len(events),
            positive=positive,
            negative=negative,
            satisfaction_rate=round(100 * positive / len(events), 2) if events else 0.0,
            corrections=corrections,
        )


feedback_service = FeedbackService()
