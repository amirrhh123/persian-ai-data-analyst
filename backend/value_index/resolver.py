"""Ground question values onto real database columns (roadmap Change 3).

Flow: extract candidates -> search the safe value index -> rank by signals ->
produce grounded filters, a table recommendation, or an ambiguity flag that the
pipeline turns into a Persian clarification question.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.value_index.extractor import (
    CandidateValue,
    extract_candidate_values,
)
from backend.value_index.models import ValueIndexSnapshot
from backend.value_index.ranker import (
    RankingOutcome,
    rank_candidate_values,
    rank_matches,
)


class GroundedFilter(BaseModel):
    """A value grounded to a concrete table.column with ranking evidence."""

    table: str
    column: str
    operator: str = "="
    value: str
    score: float = 0.0
    label_matched: bool = False
    matched_label: Optional[str] = None


class GroundingResult(BaseModel):
    """Outcome of grounding one user question."""

    grounded_filters: List[GroundedFilter] = Field(default_factory=list)
    recommended_table: Optional[str] = None
    ambiguous_tables: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def found_any(self) -> bool:
        return bool(self.grounded_filters)

    @property
    def is_ambiguous(self) -> bool:
        """More than one distinct candidate table within the tie epsilon."""
        return len(self.ambiguous_tables) > 1

    @property
    def candidate_tables(self) -> List[str]:
        """Distinct candidate tables ordered by evidence strength."""
        tables: List[str] = []
        for item in self.evidence:
            table = item.get("table")
            if table and table not in tables:
                tables.append(table)
        for item in self.grounded_filters:
            if item.table not in tables:
                tables.append(item.table)
        return tables

    def audit_payload(self) -> Dict[str, Any]:
        """Trace-safe representation; contains only indexed (safe) values."""
        return {
            "grounded_filters": [item.model_dump() for item in self.grounded_filters],
            "recommended_table": self.recommended_table,
            "ambiguous_tables": sorted(self.ambiguous_tables),
            "candidates": self.evidence,
        }


class ValueGroundingResolver:
    """Resolve question values against a tenant's safe value index."""

    def __init__(self, max_grounded_filters: int = 3) -> None:
        self.max_grounded_filters = max_grounded_filters

    def resolve(
        self,
        question: str,
        index: Optional[ValueIndexSnapshot],
        *,
        requested_entity: Optional[str] = None,
        exclude_tables: Optional[set[str]] = None,
        table_adjustments: Optional[Dict[str, float]] = None,
        search_fn=None,
    ) -> GroundingResult:
        if index is None and search_fn is None:
            return GroundingResult()

        if search_fn is None:
            from backend.value_index.service import value_index_service

            def search_fn(text: str) -> list:
                return value_index_service.search(text, index=index)

        candidates: List[CandidateValue] = extract_candidate_values(question)
        # The index performs phrase-boundary matching against the full
        # question; explicit candidates (quoted spans) only add precision.
        if not candidates:
            candidates = [CandidateValue(text=question)]

        def bounded_search(text: str) -> list:
            matches = search_fn(text)
            if exclude_tables:
                return [match for match in matches if match.table not in exclude_tables]
            return matches

        outcome: RankingOutcome = rank_candidate_values(
            question,
            candidates,
            bounded_search,
            requested_entity=requested_entity,
            table_adjustments=table_adjustments,
        )

        result = GroundingResult(
            ambiguous_tables=sorted(outcome.ambiguous_tables),
            evidence=[item.evidence() for item in outcome.ranked[:10]],
        )

        top = outcome.top
        if top is not None and not outcome.is_ambiguous:
            result.recommended_table = top.match.table

        seen: set[tuple[str, str]] = set()
        for candidate in outcome.ranked:
            key = (candidate.match.table, candidate.match.column)
            if key in seen:
                continue
            seen.add(key)
            result.grounded_filters.append(
                GroundedFilter(
                    table=candidate.match.table,
                    column=candidate.match.column,
                    operator="=",
                    value=candidate.match.value,
                    score=candidate.final_score,
                    label_matched=candidate.match.label_matched,
                    matched_label=candidate.match.matched_label,
                )
            )
            if len(result.grounded_filters) >= self.max_grounded_filters:
                break

        return result


value_grounding_resolver = ValueGroundingResolver()
