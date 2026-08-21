"""Safe query decomposition and score fusion for multi-part retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from backend.reports.hybrid_retrieval import HybridRetriever


_STRONG_BOUNDARY = re.compile(
    r"\s*(?:[؛;؟?]+|\bهمچنین\b|\bبه علاوه\b|\bعلاوه بر این\b|\bو همچنین\b)\s*"
)
_INTENT_TERMS = {
    "تعداد", "چند", "میانگین", "مجموع", "کمترین", "بیشترین",
    "فهرست", "لیست", "اطلاعات", "نام", "کدام", "مقایسه",
    "count", "average", "avg", "sum", "minimum", "maximum", "list",
}


@dataclass(frozen=True, slots=True)
class QueryDecomposition:
    """Original query plus unique retrieval-safe atomic queries."""

    original: str
    queries: tuple[str, ...]
    decomposed: bool
    reason: str


class QueryDecomposer:
    """Split only at strong boundaries or independently meaningful clauses."""

    def __init__(self, maximum_parts: int = 4) -> None:
        if maximum_parts < 1:
            raise ValueError("maximum_parts must be positive")
        self.maximum_parts = maximum_parts
        self._text = HybridRetriever()

    def _has_intent(self, text: str) -> bool:
        return bool(set(self._text.tokenize(text)) & _INTENT_TERMS)

    def _valid_part(self, text: str) -> bool:
        return len(self._text.tokenize(text)) >= 3

    @staticmethod
    def _unique(parts: Sequence[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for part in parts:
            cleaned = " ".join(part.split()).strip("،,. ")
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                unique.append(cleaned)
        return unique

    def decompose(self, question: str) -> QueryDecomposition:
        """Create bounded subqueries while preserving the original query first."""
        original = " ".join(question.split()).strip()
        if not original:
            return QueryDecomposition("", tuple(), False, "empty_query")

        parts = self._unique(_STRONG_BOUNDARY.split(original))
        reason = "strong_boundary"
        if len(parts) <= 1:
            conjunction_parts = self._unique(re.split(r"\s+و\s+", original))
            if (
                len(conjunction_parts) > 1
                and all(self._valid_part(part) and self._has_intent(part) for part in conjunction_parts)
            ):
                parts = conjunction_parts
                reason = "independent_intents"

        valid_parts = [part for part in parts if self._valid_part(part)]
        if len(valid_parts) <= 1:
            return QueryDecomposition(original, (original,), False, "single_intent")

        retrieval_queries = self._unique([original, *valid_parts])[: self.maximum_parts + 1]
        return QueryDecomposition(
            original=original,
            queries=tuple(retrieval_queries),
            decomposed=True,
            reason=reason,
        )


def fuse_vector_scores(
    score_maps: Sequence[Mapping[str, float]],
    original_weight: float = 0.60,
) -> dict[str, float]:
    """Fuse original-query evidence with the strongest atomic-query evidence."""
    if not 0 <= original_weight <= 1:
        raise ValueError("original_weight must be between zero and one")
    if not score_maps:
        return {}
    if len(score_maps) == 1:
        return dict(score_maps[0])

    candidate_ids = set().union(*(scores.keys() for scores in score_maps))
    fused: dict[str, float] = {}
    for candidate_id in candidate_ids:
        original_score = score_maps[0].get(candidate_id, 0.0)
        atomic_score = max(
            (scores.get(candidate_id, 0.0) for scores in score_maps[1:]),
            default=0.0,
        )
        fused[candidate_id] = max(
            0.0,
            min(1.0, original_weight * original_score + (1 - original_weight) * atomic_score),
        )
    return fused


query_decomposer = QueryDecomposer()
