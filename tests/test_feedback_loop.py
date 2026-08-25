"""Offline tests for the feedback -> grounding correction loop (accuracy #3)."""

from pathlib import Path
import tempfile

from backend.feedback.models import FeedbackRequest
from backend.feedback.service import FeedbackService
from backend.value_index.models import ValueIndexMatch
from backend.value_index.ranker import rank_matches
from backend.value_index.resolver import value_grounding_resolver


def _service() -> FeedbackService:
    return FeedbackService(schema_root=Path(tempfile.mkdtemp(prefix="fb_")))


def _submit(service, tenant, question, rating, served=None, corrected=None, qid="12345678"):
    request = FeedbackRequest(
        query_id=qid,
        question=question,
        rating=rating,
        served_table=served,
        corrected_table=corrected,
    )
    return service.submit(tenant, request)


# ----------------------------------------------------------------------
# table_adjustments
# ----------------------------------------------------------------------

def test_negative_with_correction_penalizes_served_and_boosts_correct():
    service = _service()
    q = "آمار تهران را نشان بده"
    _submit(service, "t", q, "negative", served="organization_units", corrected="students")
    adjustments = service.table_adjustments("t", q)
    assert adjustments["organization_units"] < 0
    assert adjustments["students"] > 0


def test_positive_reinforces_served_table():
    service = _service()
    q = "تعداد دانش آموزان"
    _submit(service, "t", q, "positive", served="students")
    adjustments = service.table_adjustments("t", q)
    assert adjustments.get("students", 0) > 0


def test_other_questions_are_not_affected():
    service = _service()
    _submit(service, "t", "سوال اول درباره کارکنان", "negative", served="employees", corrected="students")
    assert service.table_adjustments("t", "سوال کاملاً متفاوت") == {}


def test_adjustments_clamped_at_bounds():
    service = _service()
    q = "سوال تکراری"
    for i in range(8):
        _submit(service, "t", q, "negative", served="bad_table", corrected="good_table", qid=f"query-id-{i}")
    adjustments = service.table_adjustments("t", q)
    assert -0.20 <= adjustments["bad_table"] <= 0.20
    assert -0.20 <= adjustments["good_table"] <= 0.20


# ----------------------------------------------------------------------
# Ranking integration: feedback flips a near-tie
# ----------------------------------------------------------------------

def _match(table, score):
    return ValueIndexMatch(
        table=table, column="col", value="تهران", count=5, score=score
    )


def test_feedback_breaks_near_tie_in_ranker():
    matches = [_match("organization_units", 0.90), _match("students", 0.88)]
    outcome = rank_matches(matches, requested_entity=None)
    assert outcome.is_ambiguous  # genuine tie without feedback

    adjusted = rank_matches(
        matches,
        requested_entity=None,
        table_adjustments={"students": 0.12, "organization_units": -0.08},
    )
    assert not adjusted.is_ambiguous
    assert adjusted.top.match.table == "students"


def test_resolver_passes_adjustments_through():
    matches = [
        _match("table_a", 0.90),
        _match("table_b", 0.89),
    ]

    def search_fn(text):
        return matches

    result = value_grounding_resolver.resolve(
        "آمار تهران",
        index=None,
        search_fn=search_fn,
        table_adjustments={"table_b": +0.12},
    )
    assert result.recommended_table == "table_b"


def test_no_feedback_leaves_ranking_unchanged():
    matches = [_match("a", 0.9), _match("b", 0.7)]
    outcome = rank_matches(matches, table_adjustments={})
    assert outcome.top.match.table == "a"
