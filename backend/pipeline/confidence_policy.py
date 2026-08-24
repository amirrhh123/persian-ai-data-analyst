"""Confidence-based clarification policy (roadmap Change 5).

Aggregates confidence dimensions (intent, entity, plan/table, value grounding)
into one assessment with the roadmap thresholds:

    score >= 0.85            -> proceed
    0.60 <= score < 0.85     -> proceed only when a deterministic plan validates it
    score <  0.60            -> clarify

A dedicated cross-table rule fires regardless of the aggregate: when value
grounding finds near-tie evidence in different tables and no entity noun binds
the question, we ask instead of guessing.

Thresholds are intentionally module constants; calibrate them from benchmark
data (Phase 1 harness) before changing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

PROCEED_THRESHOLD = 0.85
VALIDATED_THRESHOLD = 0.60

DECISION_PROCEED = "proceed"
DECISION_PROCEED_VALIDATED = "proceed_validated"
DECISION_CLARIFY = "clarify"

# Persian nouns for candidate tables in clarification questions.
TABLE_NOUNS_FA: Dict[str, str] = {
    "students": "دانش‌آموزان",
    "employees": "کارکنان",
    "schools": "مدارس",
    "salary_items": "حقوق",
    "retirement_records": "بازنشستگی",
    "ranking_requests": "ارتقای رتبه",
    "organization_units": "واحدهای سازمانی",
    "demo_training_requests": "درخواست‌های آموزشی",
}

_DIMENSION_WEIGHTS = {
    "intent": 0.25,
    "entity": 0.20,
    "plan": 0.35,
    "value": 0.20,
}


class ConfidenceAssessment(BaseModel):
    score: float
    decision: str
    dimensions: Dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    clarification_question: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def should_clarify(self) -> bool:
        return self.decision == DECISION_CLARIFY


def table_label_fa(table_name: str) -> str:
    return TABLE_NOUNS_FA.get(table_name, table_name)


class ConfidencePolicy:
    """Stateless scorer; pipeline supplies the dimension inputs."""

    def assess(
        self,
        *,
        intent_confidence: float,
        requested_entity: Optional[str],
        has_plan: bool,
        plan_source: str,
        grounding=None,
        grounding_ambiguous_tables: Optional[List[str]] = None,
        entity_binding_present: bool = False,
        used_value_override: bool = False,
        plan_template_approved: bool = False,
    ) -> ConfidenceAssessment:
        intent_score = max(0.0, min(1.0, intent_confidence))

        if requested_entity:
            entity_score = 0.95 if (entity_binding_present or has_plan) else 0.80
        elif used_value_override or (grounding is not None and grounding.recommended_table):
            entity_score = 0.80
        else:
            entity_score = 0.50

        if not has_plan:
            plan_score = 0.35
        elif plan_source == "deterministic_normalized_intent":
            plan_score = 1.0
        else:
            plan_score = 0.80

        if grounding is None or (not grounding.found_any and not grounding.ambiguous_tables):
            value_score = 0.85  # neutral: no values were needed
        elif grounding.is_ambiguous:
            value_score = max(0.30, (grounding.grounded_filters[0].score if grounding.grounded_filters else 0.3) - 0.15)
        else:
            value_score = grounding.grounded_filters[0].score if grounding.grounded_filters else 0.85

        score = (
            _DIMENSION_WEIGHTS["intent"] * intent_score
            + _DIMENSION_WEIGHTS["entity"] * entity_score
            + _DIMENSION_WEIGHTS["plan"] * plan_score
            + _DIMENSION_WEIGHTS["value"] * value_score
        )
        score = round(max(0.0, min(1.0, score)), 4)

        candidates = self._candidate_payload(grounding)

        # Cross-table near-tie with no binding entity: always ask.
        ambiguous_cross_table = (
            grounding is not None
            and grounding.is_ambiguous
            and len({item.get("table") for item in grounding.evidence[:4]}) > 1
            and not requested_entity
            and not used_value_override
        )

        deterministic_validation = has_plan and (
            plan_source == "deterministic_normalized_intent" or plan_template_approved
        )

        if score >= PROCEED_THRESHOLD and not ambiguous_cross_table:
            return ConfidenceAssessment(
                score=score,
                decision=DECISION_PROCEED,
                dimensions=self._dimensions(intent_score, entity_score, plan_score, value_score),
                reason="اطمینان کافی برای اجرای خودکار",
                candidates=candidates,
            )

        if (
            VALIDATED_THRESHOLD <= score < PROCEED_THRESHOLD
            and deterministic_validation
            and not ambiguous_cross_table
        ):
            return ConfidenceAssessment(
                score=score,
                decision=DECISION_PROCEED_VALIDATED,
                dimensions=self._dimensions(intent_score, entity_score, plan_score, value_score),
                reason="اطمینان متوسط؛ قواعد قطعی درخواست را تأیید کردند",
                candidates=candidates,
            )

        question = self._build_clarification_question(
            grounding, ambiguous_cross_table, requested_entity, grounding_ambiguous_tables
        )
        return ConfidenceAssessment(
            score=score,
            decision=DECISION_CLARIFY,
            dimensions=self._dimensions(intent_score, entity_score, plan_score, value_score),
            reason=(
                "ارزش در چند جدول مبهم است"
                if ambiguous_cross_table
                else "اطمینان کلی پایین‌تر از حد مجاز است"
            ),
            clarification_question=question,
            candidates=candidates,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _dimensions(intent_s: float, entity_s: float, plan_s: float, value_s: float) -> Dict[str, float]:
        return {
            "intent": round(intent_s, 4),
            "entity": round(entity_s, 4),
            "plan": round(plan_s, 4),
            "value": round(value_s, 4),
        }

    @staticmethod
    def _candidate_payload(grounding) -> List[Dict[str, Any]]:
        if grounding is None:
            return []
        payload: List[Dict[str, Any]] = []
        seen = set()
        for item in grounding.evidence[:6]:
            table = item.get("table")
            if not table or table in seen:
                continue
            seen.add(table)
            payload.append(
                {
                    "table": table,
                    "label": table_label_fa(table),
                    "column": item.get("column"),
                    "value": item.get("value"),
                    "score": item.get("score"),
                }
            )
        return payload

    def _build_clarification_question(
        self,
        grounding,
        ambiguous_cross_table: bool,
        requested_entity: Optional[str],
        ambiguous_tables: Optional[List[str]] = None,
    ) -> str:
        tables: List[str] = []
        if grounding is not None and grounding.candidate_tables:
            tables = list(grounding.candidate_tables)
        if not tables and ambiguous_tables:
            tables = list(ambiguous_tables)
        if not tables and grounding is not None:
            tables = [item.get("table") for item in grounding.evidence[:4] if item.get("table")]
        labels = [table_label_fa(table) for table in dict.fromkeys(tables) if table]
        if len(labels) >= 2:
            options = "، ".join(labels[:-1]) + " یا " + labels[-1]
            return f"منظور شما آمار {options} است؟ لطفاً مشخص کنید."
        if requested_entity:
            return (
                "سؤال شما کاملاً مشخص نیست. لطفاً دقیق‌تر بگویید چه اطلاعاتی نیاز دارید "
                "(مثلاً تعداد، لیست، یا جزئیات یک مورد خاص)."
            )
        return (
            "سؤال شما قابل تفسیرهای متعددی دارد. لطفاً موضوع اصلی (دانش‌آموزان، کارکنان، "
            "مدارس و ...) و شرط موردنظر را دقیق‌تر بیان کنید."
        )


confidence_policy = ConfidencePolicy()
