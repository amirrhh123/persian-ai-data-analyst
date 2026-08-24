"""Structured required-filter contracts extracted from query intent and plans.

A contract states which predicates MUST appear in the final SQL. It is built
after planning (so planner decisions like relocating province onto
organization_units.province stay authoritative) and validated against the
generated SQL before execution. Matching is done on normalized identifiers and
values - never raw strings (roadmap Change 2).
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ZWNJ = "\u200c"

SUPPORTED_OPERATORS = {"=", "!=", "<>", ">", ">=", "<", "<=", "IN"}

# Operators rendered differently per backend/template (EXTRACT wrappers);
# they are tracked as advisory and never hard-fail a query.
ADVISORY_OPERATORS = {"YEAR=", "MONTH=", "DAY="}

# Filters whose value may legitimately contain other filter tokens
# (e.g. school name contains the word دبیرستان).
NAME_LIKE_SOURCES = {
    "school_name",
    "organization_unit_name",
    "person_name",
    "named_value",
}


def normalize_digits(text: Any) -> str:
    return str(text).translate(_PERSIAN_DIGITS)


def normalize_value(value: Any) -> str:
    """Normalize a literal value for comparison: digits, ZWNJ, quotes, spaces."""
    text = normalize_digits(value)
    text = text.replace(_ZWNJ, "")
    for quote in ("'", '"', "`"):
        text = text.replace(quote, "")
    return re.sub(r"\s+", " ", text.strip())


def normalize_column(column: Any) -> str:
    return re.sub(r"\s+", "", normalize_digits(str(column)).lower()).replace(_ZWNJ, "")


class RequiredFilter(BaseModel):
    column: str
    operator: str = "="
    value: str
    entity: Optional[str] = None
    source: str = "intent"
    source_text: Optional[str] = None
    advisory: bool = False

    @property
    def column_key(self) -> str:
        return normalize_column(self.column)

    @property
    def bare_column(self) -> str:
        return self.column_key.split(".")[-1]

    def dict_for_error(self) -> dict[str, str]:
        return {
            "column": self.column,
            "operator": self.operator,
            "value": self.value,
            "source": self.source,
        }


class FilterContract(BaseModel):
    filters: List[RequiredFilter] = Field(default_factory=list)

    def required_filters(self) -> List[RequiredFilter]:
        return [item for item in self.filters if not item.advisory]


def _iter_candidate_values(intent: Any) -> List[RequiredFilter]:
    """Collect scalar intent fields as candidate required filters."""
    candidates: List[RequiredFilter] = []

    def add(column: str, value: Any, source: str, operator: str = "=") -> None:
        if value in (None, "", []):
            return
        if isinstance(value, (list, tuple, set)):
            candidates.append(
                RequiredFilter(
                    column=column,
                    operator="IN",
                    value="|".join(str(item) for item in value),
                    source=source,
                )
            )
            return
        candidates.append(RequiredFilter(column=column, operator=operator, value=str(value), source=source))

    add("national_id", getattr(intent, "national_id", None), "national_id")
    add("province", getattr(intent, "province", None), "location")
    add("city", getattr(intent, "city", None), "location")
    for value in getattr(intent, "province_values", None) or []:
        add("province", value, "location")
    for value in getattr(intent, "city_values", None) or []:
        add("city", value, "location")
    add("status", getattr(intent, "status", None), "status")
    add("position", getattr(intent, "position", None), "position")
    add("first_name", getattr(intent, "first_name", None), "person_name")
    add("last_name", getattr(intent, "last_name", None), "person_name")
    add("grade", getattr(intent, "grade", None), "student")
    add("enrollment_year", getattr(intent, "enrollment_year", None), "student")
    add("school_name", getattr(intent, "named_school", None), "school_name")
    add("school_type", getattr(intent, "school_type", None), "school")
    add("capacity", getattr(intent, "capacity_min", None), "school", operator=">=")
    add("established_year", getattr(intent, "established_year", None), "school")
    add(
        "organization_unit_name",
        getattr(intent, "named_organization_unit", None),
        "organization_unit_name",
    )
    add("hire_year", getattr(intent, "hire_year", None), "employee")
    add("named_student", getattr(intent, "named_student", None), "person_name")

    for item in getattr(intent, "filters", None) or []:
        column = getattr(item, "column", None) or getattr(item, "field", None)
        value = getattr(item, "value", None)
        operator = getattr(item, "operator", "=") or "="
        if not column or value in (None, ""):
            continue
        candidates.append(
            RequiredFilter(
                column=str(column),
                operator=str(operator),
                value=str(value),
                source=getattr(item, "source", "intent") or "intent",
            )
        )
    return candidates


def _plan_filters(plan: Any) -> List[RequiredFilter]:
    collected: List[RequiredFilter] = []
    for item in getattr(plan, "filters", None) or []:
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        operator = str(item.get("operator", "="))
        value = item.get("value")
        if not column or value in (None, ""):
            continue
        collected.append(
            RequiredFilter(
                column=str(column),
                operator=operator,
                value=str(value),
                source="plan",
                advisory=operator in ADVISORY_OPERATORS,
            )
        )
    return collected


def _drop_subsumed(filters: List[RequiredFilter]) -> List[RequiredFilter]:
    """Remove categorical filters whose value lives inside a name-like filter.

    General rule (no person/place-specific cases): if a non-name filter's whole
    normalized value appears inside a name-like filter's value on the same
    question, it describes the name, not an independent condition.
    Example: school_type='دبیرستان' vs school_name='دبیرستان فرزانگان مرودشت'.
    """
    name_values = [
        normalize_value(item.value)
        for item in filters
        if item.source in NAME_LIKE_SOURCES
    ]
    kept: List[RequiredFilter] = []
    for item in filters:
        if item.source in NAME_LIKE_SOURCES:
            kept.append(item)
            continue
        item_text = normalize_value(item.value)
        if item_text and any(item_text in name_value for name_value in name_values if name_value != item_text):
            continue
        kept.append(item)
    return kept


def _dedupe(filters: List[RequiredFilter]) -> List[RequiredFilter]:
    seen: set[tuple[str, str, str]] = set()
    unique: List[RequiredFilter] = []
    for item in filters:
        key = (item.column_key, item.operator, normalize_value(item.value))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_filter_contract(
    intent: Any,
    plan: Any = None,
) -> FilterContract:
    """Build the required-filter contract from normalized intent plus plan."""
    candidates = _iter_candidate_values(intent)
    if plan is not None:
        candidates.extend(_plan_filters(plan))

    deduped = _dedupe(candidates)
    deduped = _drop_subsumed(deduped)

    # Plan-provided filters are authoritative for execution shape; intent-only
    # duplicates of the same predicate collapse via _dedupe above.
    return FilterContract(filters=deduped)


def contract_from_validation_result(result: Any) -> FilterContract:
    """Rebuild a contract from a failed ValidationResult's missing list."""
    filters = [
        RequiredFilter(**item)
        for item in getattr(result, "missing_required_filters", []) or []
        if isinstance(item, dict) and item.get("column")
    ]
    return FilterContract(filters=filters)
