"""Confidence policy for accepting or rejecting reranked retrieval results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.reports.reranker import RerankedResult


@dataclass(frozen=True, slots=True)
class ConfidenceDecision:
    """An auditable retrieval acceptance decision."""

    accepted: bool
    reason_code: str
    confidence: float
    margin: float
    evidence_score: float


class ConfidenceGate:
    """Fail closed when retrieval is weak or the best candidates are ambiguous."""

    def __init__(
        self,
        minimum_score: float = 0.40,
        minimum_margin: float = 0.04,
        minimum_evidence: float = 0.20,
        strong_score: float = 0.80,
    ) -> None:
        values = (minimum_score, minimum_margin, minimum_evidence, strong_score)
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("Confidence thresholds must be between zero and one")
        if strong_score < minimum_score:
            raise ValueError("Strong score cannot be lower than minimum score")
        self.minimum_score = minimum_score
        self.minimum_margin = minimum_margin
        self.minimum_evidence = minimum_evidence
        self.strong_score = strong_score

    def evaluate(self, candidates: Sequence[RerankedResult]) -> ConfidenceDecision:
        """Evaluate the top result using score, evidence, and top-two margin."""
        if not candidates:
            return ConfidenceDecision(False, "no_candidates", 0.0, 0.0, 0.0)

        best = candidates[0]
        runner_up_score = candidates[1].final_score if len(candidates) > 1 else 0.0
        margin = max(0.0, best.final_score - runner_up_score)
        evidence = max(
            best.reranker_score,
            best.source.lexical_score,
            best.features.metadata_match,
        )

        if best.final_score < self.minimum_score:
            reason = "low_score"
            accepted = False
        elif evidence < self.minimum_evidence:
            reason = "insufficient_evidence"
            accepted = False
        elif len(candidates) > 1 and margin < self.minimum_margin and best.final_score < self.strong_score:
            reason = "ambiguous_top_candidates"
            accepted = False
        else:
            reason = "accepted"
            accepted = True

        return ConfidenceDecision(
            accepted=accepted,
            reason_code=reason,
            confidence=round(best.final_score, 4),
            margin=round(margin, 4),
            evidence_score=round(evidence, 4),
        )


confidence_gate = ConfidenceGate()
