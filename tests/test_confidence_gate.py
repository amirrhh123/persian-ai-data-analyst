"""Offline tests for the confidence-based clarification gate (roadmap Change 5)."""

from backend.pipeline.clarification_state import (
    ClarificationContext,
    InMemoryClarificationStore,
)
from backend.pipeline.confidence_policy import (
    DECISION_CLARIFY,
    DECISION_PROCEED,
    DECISION_PROCEED_VALIDATED,
    confidence_policy,
    table_label_fa,
)
from backend.value_index.resolver import GroundedFilter, GroundingResult


def _grounding(scores_tables, ambiguous=None):
    filters = [
        GroundedFilter(table=t, column="col", value="تهران", score=s)
        for t, s in scores_tables
    ]
    return GroundingResult(
        grounded_filters=filters,
        recommended_table=None if ambiguous else (scores_tables[0][0] if scores_tables else None),
        ambiguous_tables=list(ambiguous or []),
        evidence=[
            {"table": t, "column": "col", "value": "تهران", "score": s}
            for t, s in scores_tables
        ],
    )


# ----------------------------------------------------------------------
# Threshold policy
# ----------------------------------------------------------------------

def test_high_confidence_deterministic_proceeds():
    assessment = confidence_policy.assess(
        intent_confidence=0.95,
        requested_entity="student",
        has_plan=True,
        plan_source="deterministic_normalized_intent",
        grounding=None,
        entity_binding_present=True,
    )
    assert assessment.decision == DECISION_PROCEED


def test_mid_band_without_deterministic_validation_clarifies():
    assessment = confidence_policy.assess(
        intent_confidence=0.60,
        requested_entity=None,
        has_plan=True,
        plan_source="legacy",
        grounding=_grounding([("t1", 0.65)]),
    )
    assert assessment.decision == DECISION_CLARIFY


def test_mid_band_with_template_approval_proceeds_validated():
    assessment = confidence_policy.assess(
        intent_confidence=0.75,
        requested_entity=None,
        has_plan=True,
        plan_source="legacy",
        grounding=_grounding([("demo_training_requests", 0.68)]),
        used_value_override=True,
        plan_template_approved=True,
    )
    assert assessment.decision == DECISION_PROCEED_VALIDATED


def test_low_intent_confidence_clarifies_even_with_plan():
    assessment = confidence_policy.assess(
        intent_confidence=0.30,
        requested_entity=None,
        has_plan=False,
        plan_source="none",
        grounding=None,
    )
    assert assessment.decision == DECISION_CLARIFY
    assert assessment.clarification_question  # Persian question present


# ----------------------------------------------------------------------
# Cross-table ambiguity rule
# ----------------------------------------------------------------------

def test_cross_table_near_tie_always_asks_when_no_entity():
    assessment = confidence_policy.assess(
        intent_confidence=0.95,
        requested_entity=None,
        has_plan=True,
        plan_source="deterministic_normalized_intent",
        grounding=_grounding(
            [("organization_units", 0.99), ("demo_training_requests", 0.97)],
            ambiguous=["organization_units", "demo_training_requests"],
        ),
    )
    assert assessment.decision == DECISION_CLARIFY
    assert "منظور شما" in (assessment.clarification_question or "")


def test_cross_table_rule_respects_value_override_and_entity():
    # Entity bound + value override already applied: no forced clarification.
    assessment = confidence_policy.assess(
        intent_confidence=0.95,
        requested_entity="employee",
        has_plan=True,
        plan_source="deterministic_normalized_intent",
        grounding=_grounding(
            [("employees", 0.99), ("demo_training_requests", 0.98)],
            ambiguous=["employees", "demo_training_requests"],
        ),
        entity_binding_present=True,
        used_value_override=True,
    )
    assert assessment.decision != DECISION_CLARIFY


# ----------------------------------------------------------------------
# Clarification question quality
# ----------------------------------------------------------------------

def test_clarification_question_lists_persian_candidates():
    assessment = confidence_policy.assess(
        intent_confidence=0.9,
        requested_entity=None,
        has_plan=True,
        plan_source="deterministic_normalized_intent",
        grounding=_grounding(
            [("students", 0.99), ("employees", 0.98)],
            ambiguous=["students", "employees"],
        ),
    )
    question = assessment.clarification_question or ""
    assert "دانش\u200cآموزان" in question
    assert "کارکنان" in question


def test_table_label_fallback_is_raw_name():
    assert table_label_fa("unknown_table") == "unknown_table"
    assert table_label_fa("students") == "دانش\u200cآموزان"


# ----------------------------------------------------------------------
# Clarification state store / resume
# ----------------------------------------------------------------------

def test_store_save_pop_roundtrip():
    store = InMemoryClarificationStore()
    ctx = ClarificationContext(
        session_id="s1",
        original_question="آمار تهران را نشان بده",
        candidates=[{"table": "students", "label": "دانش‌آموزان"}],
        missing_decision="entity",
    )
    store.save(ctx)
    peeked = store.peek("s1")
    assert peeked is not None and peeked.original_question.startswith("آمار")
    popped = store.pop("s1")
    assert popped is not None
    assert store.peek("s1") is None  # consumed -> session ends


def test_store_missing_session_returns_none():
    store = InMemoryClarificationStore()
    assert store.peek("nope") is None
    assert store.pop("nope") is None


def test_store_ttl_expiry(monkeypatch):
    import time

    store = InMemoryClarificationStore(ttl_seconds=10)
    ctx = ClarificationContext(session_id="old", original_question="q")
    store.save(ctx)
    # Simulate aging beyond TTL.
    stored = store._items["old"]
    object.__setattr__(stored, "created_at", time.time() - 100)
    assert store.peek("old") is None
