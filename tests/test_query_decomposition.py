"""Tests for safe multi-part retrieval query decomposition."""

import pytest

from backend.reports.query_decomposition import QueryDecomposer, fuse_vector_scores


def test_decomposes_strong_persian_boundary() -> None:
    result = QueryDecomposer().decompose(
        "تعداد دانش آموزان تهران؛ همچنین میانگین حقوق کارمندان اصفهان"
    )
    assert result.decomposed is True
    assert result.reason == "strong_boundary"
    assert result.queries[0].startswith("تعداد دانش آموزان")
    assert "تعداد دانش آموزان تهران" in result.queries
    assert "میانگین حقوق کارمندان اصفهان" in result.queries


def test_does_not_split_name_and_family_name() -> None:
    result = QueryDecomposer().decompose("نام و نام خانوادگی کارمند نسرین هاشمی")
    assert result.decomposed is False
    assert result.queries == ("نام و نام خانوادگی کارمند نسرین هاشمی",)


def test_decomposes_independent_intents_joined_by_and() -> None:
    result = QueryDecomposer().decompose(
        "تعداد دانش آموزان استان تهران و میانگین حقوق کارمندان استان تهران"
    )
    assert result.decomposed is True
    assert result.reason == "independent_intents"


def test_empty_query_has_no_retrieval_queries() -> None:
    result = QueryDecomposer().decompose("   ")
    assert result.queries == tuple()
    assert result.reason == "empty_query"


def test_score_fusion_preserves_original_and_atomic_evidence() -> None:
    fused = fuse_vector_scores([
        {"student": 0.6, "employee": 0.5},
        {"student": 0.9, "employee": 0.2},
    ])
    assert fused["student"] == pytest.approx(0.72)
    assert fused["employee"] == pytest.approx(0.38)


def test_score_fusion_validates_weight() -> None:
    with pytest.raises(ValueError):
        fuse_vector_scores([{}], original_weight=1.1)
