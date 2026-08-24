"""Validate that generated SQL satisfies every required-filter contract entry.

Matching is semantic, not textual:
- Persian/Arabic digits are normalized on both sides.
- Quotes and whitespace are ignored.
- Table aliases are resolved before column comparison.
- ``=`` is satisfied by an equivalent ``IN`` list or a repeated-``OR`` chain
  on the same column (roadmap Change 2 equivalence rules).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from backend.sql.filter_contract import (
    FilterContract,
    RequiredFilter,
    normalize_value,
)
from backend.sql.models import ValidationResult

_IDENTIFIER = r"[a-zA-Z_\u0600-\u06EF][a-zA-Z0-9_\u0600-\u06EF]*"
_QUALIFIED = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})?"
_LITERAL = r"'(?:[^']*)'|[0-9][0-9,._]*|[^\s(),;]+"
_NON_KEYWORD = {
    "on", "where", "and", "or", "not", "in", "like", "between", "is", "null",
    "group", "order", "by", "limit", "having", "join", "from", "select",
}
_FLIPPED = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}

# Intent field names that surface under different physical column names;
# bare hint names match any table qualifier.
_FIELD_COLUMN_HINTS: Dict[str, Set[str]] = {
    "school_name": {"name"},
    "organization_unit_name": {"name"},
    "named_student": {"first_name"},
    "capacity": {"capacity"},
}


def _normalize_sql_text(sql: str) -> str:
    """Digit-normalize and collapse whitespace while PRESERVING string quotes."""
    from backend.sql.filter_contract import normalize_digits

    return re.sub(r"\s+", " ", str(sql).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))


def _canonical_literal(value: Any) -> str:
    """Canonical form of a literal: quotes/ZWNJ stripped, separators removed."""
    text = normalize_value(value)
    return re.sub(r"[,\s_]", "", text)


class RequiredFilterValidator:
    def validate(
        self,
        sql: str,
        contract: FilterContract,
        schema: Any = None,
    ) -> ValidationResult:
        missing: List[RequiredFilter] = []
        required_items = contract.required_filters()
        if required_items:
            predicates = self._extract_predicates(sql)
            for required in required_items:
                if not self._satisfies(predicates, required):
                    missing.append(required)

        errors = [
            f"فیلتر ضروری در SQL وجود ندارد: {item.column} {item.operator} {item.value}"
            for item in missing
        ]
        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=[],
            missing_required_filters=[item.dict_for_error() for item in missing],
        )

    # ------------------------------------------------------------------
    # Predicate extraction
    # ------------------------------------------------------------------

    def _aliases(self, sql: str) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        pattern = rf"\b(?:FROM|JOIN)\s+({_IDENTIFIER})(?:\s+(?:AS\s+)?({_IDENTIFIER}))?"
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            table = match.group(1).lower()
            alias = (match.group(2) or "").lower()
            if alias and alias not in _NON_KEYWORD:
                aliases[alias] = table
        return aliases

    def _resolve_column(self, raw: str, aliases: Dict[str, str]) -> tuple[str, str]:
        """Return (resolved_table_or_empty, bare_column) with aliases applied."""
        text = re.sub(r'["`\[\]]', "", raw.strip())
        if "." in text:
            qualifier, _, bare = text.rpartition(".")
            return aliases.get(qualifier.lower(), qualifier.lower()), bare.lower()
        return "", text.lower()

    def _extract_predicates(self, sql: str) -> List[Dict[str, Any]]:
        normalized_sql = _normalize_sql_text(sql)
        aliases = self._aliases(sql)

        comparisons: List[Dict[str, Any]] = []
        chains: Dict[tuple[str, str], Set[str]] = {}

        comparison_pattern = (
            rf"({_QUALIFIED})\s*(=|>=|<=|<>|!=|>|<)\s*({_LITERAL})"
        )
        for match in re.finditer(comparison_pattern, normalized_sql, flags=re.IGNORECASE):
            table, bare = self._resolve_column(match.group(1), aliases)
            operator = match.group(2)
            if operator == "!=":
                operator = "<>"
            value = _canonical_literal(match.group(3))
            comparisons.append(
                {
                    "table": table,
                    "column": bare,
                    "operator": operator,
                    "value": value,
                }
            )
            if operator == "=" and self._within_or_group(normalized_sql, match.start()):
                chains.setdefault((table, bare), set()).add(value)
        for key, values in chains.items():
            if len(values) > 1:
                comparisons.append(
                    {"table": key[0], "column": key[1], "operator": "IN", "values": set(values)}
                )

        for match in re.finditer(
            rf"({_QUALIFIED})\s+in\s*\(([^)]*)\)",
            normalized_sql,
            flags=re.IGNORECASE,
        ):
            table, bare = self._resolve_column(match.group(1), aliases)
            values = {
                _canonical_literal(item)
                for item in re.split(r"\s*,\s*", match.group(2))
                if item.strip()
            }
            comparisons.append(
                {"table": table, "column": bare, "operator": "IN", "values": values}
            )

        for match in re.finditer(rf"({_QUALIFIED})\s+i?like\s+'([^']*)'", normalized_sql, flags=re.IGNORECASE):
            table, bare = self._resolve_column(match.group(1), aliases)
            comparisons.append(
                {
                    "table": table,
                    "column": bare,
                    "operator": "LIKE",
                    "value": _canonical_literal(match.group(2)),
                }
            )

        return comparisons

    @staticmethod
    def _within_or_group(text: str, position: int) -> bool:
        """True when the comparison at `position` sits inside an OR chain."""
        lowered = text.lower()
        segment_start = max(lowered.rfind(" where ", 0, position), lowered.rfind(" and ", 0, position))
        segment = lowered[segment_start:position]
        return " or " in segment

    # ------------------------------------------------------------------
    # Satisfaction checks
    # ------------------------------------------------------------------

    @staticmethod
    def _column_matches(predicate: Dict[str, Any], required: RequiredFilter) -> bool:
        bare = required.bare_column
        candidate_bares = {bare} | _FIELD_COLUMN_HINTS.get(bare, set())
        if predicate["column"] not in candidate_bares:
            return False
        required_table = required.column_key.split(".")[0] if "." in required.column_key else ""
        # Hint-based matches are bare-name matches; skip table comparison.
        if bare not in candidate_bares or predicate["column"] != bare:
            return True
        predicate_table = predicate.get("table") or ""
        if not required_table or not predicate_table:
            return True
        return required_table == predicate_table

    @staticmethod
    def _value_variants(required: RequiredFilter) -> Set[str]:
        base = _canonical_literal(required.value)
        variants = {base}
        if required.operator == "IN":
            variants.update(part for part in base.split("|") if part)
        return {variant for variant in variants if variant}

    def _satisfies(self, predicates: List[Dict[str, Any]], required: RequiredFilter) -> bool:
        wanted_values = self._value_variants(required)
        return any(
            self._predicate_satisfies(predicate, required.operator, wanted_values)
            for predicate in predicates
            if self._column_matches(predicate, required)
        )

    def _predicate_satisfies(
        self,
        predicate: Dict[str, Any],
        wanted_operator: str,
        wanted_values: Set[str],
    ) -> bool:
        actual_operator = predicate["operator"]

        if actual_operator == "IN":
            if wanted_operator != "=":
                return False
            return bool(set(predicate.get("values") or []) & wanted_values)

        if actual_operator == "LIKE":
            if wanted_operator != "=":
                return False
            stripped = (predicate.get("value") or "").strip("%")
            return bool(stripped) and stripped in wanted_values

        actual_value = predicate.get("value")
        if actual_value is None:
            return False

        if wanted_operator.upper() in ("LIKE", "ILIKE"):
            # An exact equality is strictly stronger than a pattern match;
            # a wildcard LIKE containing the value also satisfies it.
            if actual_operator == "=":
                return actual_value in wanted_values
            if actual_operator == "LIKE":
                stripped = actual_value.strip("%")
                return bool(stripped) and stripped in wanted_values
            return False

        if wanted_operator == "=":
            return actual_value in wanted_values

        if wanted_operator in ("<>", "!="):
            return actual_operator == "<>" and actual_value in wanted_values

        if actual_operator == wanted_operator:
            return actual_value in wanted_values
        if actual_operator == _FLIPPED.get(wanted_operator):
            # Mirrored literal-on-left form cannot be confirmed reliably;
            # report unsatisfied rather than guess.
            return False
        return False


required_filter_validator = RequiredFilterValidator()
