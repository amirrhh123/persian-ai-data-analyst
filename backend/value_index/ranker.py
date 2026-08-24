"""Rank grounded value candidates using roadmap Change 3 signals.

Signals (in order of weight):
- exact normalized value match (guaranteed by the index search itself)
- label proximity: a semantic column alias co-occurs with the value
- entity relevance: candidate table matches the detected request entity
- frequency and length heuristics from the base index score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.value_index.extractor import CandidateValue
from backend.value_index.models import ValueIndexMatch


# Semantic catalog entity -> primary table name.
ENTITY_PRIMARY_TABLES: Dict[str, str] = {
    "student": "students",
    "employee": "employees",
    "school": "schools",
    "salary": "salary_items",
    "retirement": "retirement_records",
    "ranking": "ranking_requests",
    "organization": "organization_units",
}

_AMBIGUITY_EPSILON = 0.08


@dataclass
class RankedCandidate:
    match: ValueIndexMatch
    final_score: float
    entity_relevant: bool = False

    def evidence(self) -> dict:
        return {
            "table": self.match.table,
            "column": self.match.column,
            "value": self.match.value,
            "score": round(self.final_score, 4),
            "label_matched": self.match.label_matched,
            "matched_label": self.match.matched_label,
            "count": self.match.count,
        }


@dataclass
class RankingOutcome:
    ranked: List[RankedCandidate] = field(default_factory=list)
    ambiguous_tables: set[str] = field(default_factory=set)

    @property
    def top(self) -> Optional[RankedCandidate]:
        return self.ranked[0] if self.ranked else None

    @property
    def is_ambiguous(self) -> bool:
        return len(self.ambiguous_tables) > 1


def rank_matches(
    matches: List[ValueIndexMatch],
    *,
    requested_entity: Optional[str] = None,
) -> RankingOutcome:
    """Apply the ranking signals to raw value-index matches."""
    primary_table = ENTITY_PRIMARY_TABLES.get(requested_entity or "", "")
    ranked: List[RankedCandidate] = []

    for match in matches:
        score = float(match.score)
        entity_relevant = bool(primary_table) and match.table == primary_table
        if entity_relevant:
            score += 0.10
        if match.label_matched:
            score += 0.05
        ranked.append(
            RankedCandidate(
                match=match,
                final_score=min(1.0, round(score, 4)),
                entity_relevant=entity_relevant,
            )
        )

    ranked.sort(key=lambda item: item.final_score, reverse=True)

    outcome = RankingOutcome(ranked=ranked)
    if ranked:
        best_score = ranked[0].final_score
        top_tables = {
            item.match.table for item in ranked if best_score - item.final_score <= _AMBIGUITY_EPSILON
        }
        outcome.ambiguous_tables = top_tables
    return outcome


def rank_candidate_values(
    question: str,
    candidates: List[CandidateValue],
    search_fn,
    *,
    requested_entity: Optional[str] = None,
) -> RankingOutcome:
    """Search the value index for each extracted candidate and rank results."""
    all_matches: List[ValueIndexMatch] = []
    seen_keys = set()
    for candidate in candidates:
        for match in search_fn(candidate.text):
            key = (match.table, match.column, match.value)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_matches.append(match)
    return rank_matches(all_matches, requested_entity=requested_entity)
