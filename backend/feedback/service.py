"""Persist feedback safely and derive bounded retrieval adjustments."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backend.feedback.models import FeedbackEvent, FeedbackRequest, FeedbackResponse, FeedbackSummary


class FeedbackService:
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
        redacted = re.sub(r"\b[0-9۰-۹]{10}\b", "***", question)
        return re.sub(r"'(?:''|[^'])*'", "'***'", redacted)

    def load(self, tenant_id: str) -> list[FeedbackEvent]:
        path = self.path(tenant_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            return [FeedbackEvent.model_validate(item) for item in json.load(file)]

    def _save(self, tenant_id: str, events: list[FeedbackEvent]) -> None:
        path = self.path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump([event.model_dump(mode="json") for event in events], file, ensure_ascii=False, indent=2)
        temporary.replace(path)

    def submit(self, tenant_id: str, request: FeedbackRequest) -> FeedbackResponse:
        events = self.load(tenant_id)
        event = FeedbackEvent(
            id=str(uuid4()), query_id=request.query_id, tenant_id=tenant_id,
            created_at=datetime.now(), question_fingerprint=self.fingerprint(request.question),
            question_redacted=self.redact_question(request.question), rating=request.rating,
            selected_group=request.selected_group, selected_report=request.selected_report,
            corrected_group=request.corrected_group, corrected_report=request.corrected_report,
            comment=request.comment.strip() if request.comment else None,
        )
        events = [item for item in events if item.query_id != request.query_id]
        events.append(event)
        self._save(tenant_id, events)
        return FeedbackResponse(status="saved", feedback_id=event.id, message="Feedback saved; only bounded retrieval ranking is affected.")

    def candidate_adjustments(self, tenant_id: str, question: str, target_type: str) -> dict[str, float]:
        if target_type not in {"group", "report"}:
            raise ValueError("target_type must be group or report")
        fingerprint = self.fingerprint(question)
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for event in self.load(tenant_id):
            if event.question_fingerprint != fingerprint:
                continue
            selected = getattr(event, f"selected_{target_type}")
            corrected = getattr(event, f"corrected_{target_type}")
            if selected:
                totals[selected] = totals.get(selected, 0.0) + (0.04 if event.rating == "positive" else -0.06)
                counts[selected] = counts.get(selected, 0) + 1
            if corrected and event.rating == "negative":
                totals[corrected] = totals.get(corrected, 0.0) + 0.08
                counts[corrected] = counts.get(corrected, 0) + 1
        return {candidate: round(max(-0.15, min(0.15, total / counts[candidate])), 4) for candidate, total in totals.items()}

    def summary(self, tenant_id: str) -> FeedbackSummary:
        events = self.load(tenant_id)
        positive = sum(event.rating == "positive" for event in events)
        return FeedbackSummary(
            tenant_id=tenant_id, total=len(events), positive=positive,
            negative=len(events) - positive,
            satisfaction_rate=round(100 * positive / len(events), 2) if events else 0.0,
            corrections=sum(bool(event.corrected_group or event.corrected_report) for event in events),
        )


feedback_service = FeedbackService()
