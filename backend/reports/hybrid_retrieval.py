"""Deterministic hybrid ranking for Persian retrieval candidates."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_CHAR_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "‌": " ",
    }
)
_TOKEN_PATTERN = re.compile(r"[\w]+", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    """A document that can be ranked by semantic and lexical evidence."""

    id: str
    document: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """A ranked candidate with auditable component scores."""

    candidate: HybridCandidate
    vector_score: float
    lexical_score: float
    final_score: float


class HybridRetriever:
    """Combine dense-vector similarity with normalized BM25-style relevance."""

    def __init__(
        self,
        vector_weight: float = 0.65,
        lexical_weight: float = 0.35,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """Initialize ranker weights.

        Args:
            vector_weight: Relative contribution from dense retrieval.
            lexical_weight: Relative contribution from lexical retrieval.
            k1: BM25 term-frequency saturation parameter.
            b: BM25 document-length normalization parameter.

        Raises:
            ValueError: If weights or BM25 parameters are invalid.
        """
        if vector_weight < 0 or lexical_weight < 0:
            raise ValueError("Hybrid retrieval weights cannot be negative")
        weight_total = vector_weight + lexical_weight
        if weight_total <= 0:
            raise ValueError("At least one hybrid retrieval weight must be positive")
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Invalid BM25 parameters")

        self.vector_weight = vector_weight / weight_total
        self.lexical_weight = lexical_weight / weight_total
        self.k1 = k1
        self.b = b

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize Persian/Arabic characters, digits, and separators."""
        normalized = text.translate(_CHAR_TRANSLATION).casefold()
        normalized = re.sub(r"[_\-/]+", " ", normalized)
        return " ".join(normalized.split())

    def tokenize(self, text: str) -> list[str]:
        """Tokenize normalized Persian and identifier text."""
        return _TOKEN_PATTERN.findall(self.normalize(text))

    @staticmethod
    def _metadata_text(metadata: Mapping[str, Any]) -> str:
        """Flatten scalar metadata values for exact identifier matching."""
        return " ".join(
            str(value)
            for value in metadata.values()
            if isinstance(value, (str, int, float)) and str(value).strip()
        )

    def _lexical_scores(
        self,
        query: str,
        candidates: Sequence[HybridCandidate],
    ) -> dict[str, float]:
        """Calculate normalized BM25 scores with an exact-phrase bonus."""
        query_tokens = self.tokenize(query)
        if not query_tokens or not candidates:
            return {candidate.id: 0.0 for candidate in candidates}

        documents = {
            candidate.id: self.tokenize(
                f"{candidate.document} {self._metadata_text(candidate.metadata)}"
            )
            for candidate in candidates
        }
        document_count = len(documents)
        average_length = sum(len(tokens) for tokens in documents.values()) / max(
            document_count, 1
        )
        document_frequency = Counter(
            token
            for token in set(query_tokens)
            for tokens in documents.values()
            if token in tokens
        )
        raw_scores: dict[str, float] = {}
        normalized_query = self.normalize(query)

        for candidate in candidates:
            tokens = documents[candidate.id]
            frequencies = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if frequency == 0:
                    continue
                frequency_in_documents = document_frequency[token]
                inverse_document_frequency = math.log(
                    1 + (document_count - frequency_in_documents + 0.5)
                    / (frequency_in_documents + 0.5)
                )
                length_ratio = len(tokens) / average_length if average_length else 0.0
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length_ratio
                )
                score += inverse_document_frequency * (
                    frequency * (self.k1 + 1) / denominator
                )

            searchable_text = self.normalize(
                f"{candidate.document} {self._metadata_text(candidate.metadata)}"
            )
            if normalized_query and normalized_query in searchable_text:
                score += 1.0
            raw_scores[candidate.id] = score

        maximum = max(raw_scores.values(), default=0.0)
        if maximum <= 0:
            return {candidate.id: 0.0 for candidate in candidates}
        return {
            candidate_id: score / maximum
            for candidate_id, score in raw_scores.items()
        }

    def rank(
        self,
        query: str,
        candidates: Sequence[HybridCandidate],
        vector_scores: Mapping[str, float],
    ) -> list[HybridSearchResult]:
        """Rank candidates by weighted dense and lexical evidence."""
        if not candidates:
            return []

        lexical_scores = self._lexical_scores(query, candidates)
        ranked: list[HybridSearchResult] = []
        for candidate in candidates:
            vector_score = max(0.0, min(1.0, vector_scores.get(candidate.id, 0.0)))
            lexical_score = lexical_scores.get(candidate.id, 0.0)
            final_score = (
                self.vector_weight * vector_score
                + self.lexical_weight * lexical_score
            )
            ranked.append(
                HybridSearchResult(
                    candidate=candidate,
                    vector_score=round(vector_score, 4),
                    lexical_score=round(lexical_score, 4),
                    final_score=round(max(0.0, min(1.0, final_score)), 4),
                )
            )

        return sorted(
            ranked,
            key=lambda result: (
                result.final_score,
                result.lexical_score,
                result.vector_score,
                result.candidate.id,
            ),
            reverse=True,
        )


hybrid_retriever = HybridRetriever()
