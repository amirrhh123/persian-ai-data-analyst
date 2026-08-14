"""Second-stage, explainable reranking for retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from backend.reports.hybrid_retrieval import HybridRetriever, HybridSearchResult


_NAME_FIELDS = {
    "name", "title", "report_name", "group_name", "table_name",
    "column_name", "report_id", "group_id",
}


@dataclass(frozen=True, slots=True)
class RerankFeatures:
    """Auditable evidence used by the second-stage ranker."""

    token_coverage: float
    exact_phrase: float
    metadata_match: float


@dataclass(frozen=True, slots=True)
class RerankedResult:
    """A hybrid result with second-stage relevance evidence."""

    source: HybridSearchResult
    features: RerankFeatures
    reranker_score: float
    final_score: float


class RetrievalReranker:
    """Rerank a small hybrid shortlist without another heavyweight model."""

    def __init__(
        self,
        hybrid_weight: float = 0.60,
        coverage_weight: float = 0.20,
        phrase_weight: float = 0.10,
        metadata_weight: float = 0.10,
    ) -> None:
        weights = (hybrid_weight, coverage_weight, phrase_weight, metadata_weight)
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError("Reranker weights must be non-negative and non-zero")
        total = sum(weights)
        self.hybrid_weight = hybrid_weight / total
        self.coverage_weight = coverage_weight / total
        self.phrase_weight = phrase_weight / total
        self.metadata_weight = metadata_weight / total
        self._text = HybridRetriever()

    def _token_coverage(self, query: str, searchable_text: str) -> float:
        query_tokens = set(self._text.tokenize(query))
        if not query_tokens:
            return 0.0
        candidate_tokens = set(self._text.tokenize(searchable_text))
        return len(query_tokens & candidate_tokens) / len(query_tokens)

    def _metadata_match(self, query: str, metadata: Mapping[str, Any]) -> float:
        normalized_query = self._text.normalize(query)
        if not normalized_query:
            return 0.0
        best = 0.0
        for key, value in metadata.items():
            if value is None or isinstance(value, (dict, list, tuple, set)):
                continue
            normalized_value = self._text.normalize(str(value))
            if not normalized_value:
                continue
            if normalized_value == normalized_query:
                score = 1.0
            elif normalized_value in normalized_query:
                score = 1.0 if key.casefold() in _NAME_FIELDS else 0.75
            else:
                score = self._token_coverage(query, normalized_value) * 0.5
            best = max(best, score)
        return best

    @staticmethod
    def _metadata_text(metadata: Mapping[str, Any]) -> str:
        return " ".join(
            str(value) for value in metadata.values()
            if isinstance(value, (str, int, float)) and str(value).strip()
        )

    def rerank(
        self,
        query: str,
        candidates: Sequence[HybridSearchResult],
        limit: int | None = None,
    ) -> list[RerankedResult]:
        """Return a stable second-stage ordering for a hybrid shortlist."""
        ranked: list[RerankedResult] = []
        normalized_query = self._text.normalize(query)
        for item in candidates:
            searchable_text = (
                f"{item.candidate.document} "
                f"{self._metadata_text(item.candidate.metadata)}"
            )
            normalized_text = self._text.normalize(searchable_text)
            coverage = self._token_coverage(query, searchable_text)
            phrase = float(bool(normalized_query and normalized_query in normalized_text))
            metadata = self._metadata_match(query, item.candidate.metadata)
            reranker_score = (
                self.coverage_weight * coverage
                + self.phrase_weight * phrase
                + self.metadata_weight * metadata
            ) / (self.coverage_weight + self.phrase_weight + self.metadata_weight)
            final_score = (
                self.hybrid_weight * item.final_score
                + self.coverage_weight * coverage
                + self.phrase_weight * phrase
                + self.metadata_weight * metadata
            )
            ranked.append(RerankedResult(
                source=item,
                features=RerankFeatures(
                    token_coverage=round(coverage, 4),
                    exact_phrase=round(phrase, 4),
                    metadata_match=round(metadata, 4),
                ),
                reranker_score=round(reranker_score, 4),
                final_score=round(max(0.0, min(1.0, final_score)), 4),
            ))

        ranked.sort(key=lambda item: (
            item.final_score, item.reranker_score,
            item.source.final_score, item.source.candidate.id,
        ), reverse=True)
        return ranked[:limit] if limit is not None else ranked


retrieval_reranker = RetrievalReranker()
