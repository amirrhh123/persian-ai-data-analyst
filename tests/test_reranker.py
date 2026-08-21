"""Tests for the explainable retrieval reranker."""

import pytest

from backend.reports.hybrid_retrieval import HybridCandidate, HybridSearchResult
from backend.reports.reranker import RetrievalReranker


def _result(
    candidate_id: str,
    document: str,
    score: float,
    metadata: dict[str, str] | None = None,
) -> HybridSearchResult:
    return HybridSearchResult(
        candidate=HybridCandidate(
            id=candidate_id,
            document=document,
            metadata=metadata or {},
        ),
        vector_score=score,
        lexical_score=score,
        final_score=score,
    )


def test_reranker_promotes_complete_query_coverage() -> None:
    reranker = RetrievalReranker()
    candidates = [
        _result("generic", "اطلاعات کارکنان سازمان", 0.82),
        _result("exact", "تعداد درخواست ها با پست کارمند اداری", 0.70),
    ]

    ranked = reranker.rerank("تعداد درخواست ها با پست کارمند اداری", candidates)

    assert ranked[0].source.candidate.id == "exact"
    assert ranked[0].features.token_coverage == 1.0
    assert ranked[0].features.exact_phrase == 1.0


def test_reranker_uses_identifier_metadata() -> None:
    reranker = RetrievalReranker()
    candidates = [
        _result("other", "گزارش عمومی", 0.75, {"report_id": "employee_list"}),
        _result("salary", "گزارش مالی", 0.68, {"report_id": "salary_summary"}),
    ]

    ranked = reranker.rerank("گزارش salary_summary", candidates)

    assert ranked[0].source.candidate.id == "salary"
    assert ranked[0].features.metadata_match == 1.0


def test_reranker_is_stable_and_supports_limit() -> None:
    reranker = RetrievalReranker()
    candidates = [_result("a", "یکسان", 0.5), _result("b", "یکسان", 0.5)]

    ranked = reranker.rerank("نامرتبط", candidates, limit=1)

    assert len(ranked) == 1
    assert ranked[0].source.candidate.id == "b"


def test_reranker_rejects_invalid_weights() -> None:
    with pytest.raises(ValueError):
        RetrievalReranker(hybrid_weight=-1)
