"""Behavior tests for retrieval confidence gating."""

import pytest

from backend.reports.confidence_gate import ConfidenceGate
from backend.reports.hybrid_retrieval import HybridCandidate, HybridSearchResult
from backend.reports.reranker import RerankFeatures, RerankedResult


def _candidate(candidate_id: str, final_score: float,
               reranker_score: float = 0.6,
               lexical_score: float = 0.5) -> RerankedResult:
    source = HybridSearchResult(
        candidate=HybridCandidate(id=candidate_id, document="test", metadata={}),
        vector_score=final_score,
        lexical_score=lexical_score,
        final_score=final_score,
    )
    return RerankedResult(
        source=source,
        features=RerankFeatures(0.5, 0.0, 0.0),
        reranker_score=reranker_score,
        final_score=final_score,
    )


def test_gate_accepts_clear_supported_winner() -> None:
    decision = ConfidenceGate().evaluate([
        _candidate("employee", 0.72), _candidate("student", 0.55),
    ])
    assert decision.accepted is True
    assert decision.reason_code == "accepted"
    assert decision.margin == 0.17


def test_gate_rejects_low_score() -> None:
    decision = ConfidenceGate().evaluate([_candidate("weak", 0.30)])
    assert decision.accepted is False
    assert decision.reason_code == "low_score"


def test_gate_rejects_ambiguous_top_candidates() -> None:
    decision = ConfidenceGate().evaluate([
        _candidate("a", 0.62), _candidate("b", 0.60),
    ])
    assert decision.accepted is False
    assert decision.reason_code == "ambiguous_top_candidates"


def test_gate_rejects_missing_evidence() -> None:
    decision = ConfidenceGate().evaluate([
        _candidate("weak", 0.65, reranker_score=0.1, lexical_score=0.1),
    ])
    assert decision.accepted is False
    assert decision.reason_code == "insufficient_evidence"


def test_gate_rejects_empty_candidates() -> None:
    decision = ConfidenceGate().evaluate([])
    assert decision.accepted is False
    assert decision.reason_code == "no_candidates"


def test_gate_validates_thresholds() -> None:
    with pytest.raises(ValueError):
        ConfidenceGate(minimum_score=1.1)
