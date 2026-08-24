"""Extract candidate literal values from a Persian natural-language question.

Extraction is intentionally generic: quoted spans and unit-suffixed numbers.
Everything else (which real database values exist) is discovered by searching
the safe value index - not guessed here.
"""

from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_UNIT_MULTIPLIERS = {
    "میلیارد": 1_000_000_000,
    "میلیون": 1_000_000,
    "هزار": 1_000,
}


class CandidateValue(BaseModel):
    """A raw literal mention extracted from the question text."""

    text: str
    kind: str = "text"  # text | number
    numeric_value: float | None = None
    span_text: str = ""


class NumericPhrase(BaseModel):
    """A quantity expression such as «۸۰ میلیون» resolved to a number."""

    raw_text: str
    amount: float
    comparison_hint: str | None = None  # کمتر از -> "<", بیشتر از -> ">"


def extract_candidate_values(question: str) -> List[CandidateValue]:
    """Return quoted strings and unit quantities mentioned in the question."""
    candidates: List[CandidateValue] = []

    quoted_pattern = re.compile(r"[«\"']([^«»\"']{2,80})[»\"']")
    for match in quoted_pattern.finditer(question):
        text = match.group(1).strip()
        if text:
            candidates.append(CandidateValue(text=text, kind="text", span_text=match.group(0)))

    return candidates


def extract_numeric_phrases(question: str) -> List[NumericPhrase]:
    """Resolve «عدد + واحد» phrases (and bare digits) into concrete amounts."""
    phrases: List[NumericPhrase] = []
    translated = question.translate(_PERSIAN_DIGITS)

    unit_alternation = "|".join(_UNIT_MULTIPLIERS)
    pattern = re.compile(
        rf"(کمتر|بیشتر)?\s*(?:از)?\s*(\d+(?:\.\d+)?)\s*({unit_alternation})?",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(translated):
        amount_text = match.group(2)
        if not amount_text:
            continue
        cleaned = amount_text.replace(",", "")
        try:
            amount = float(cleaned)
        except ValueError:
            continue
        unit = (match.group(3) or "").lower()
        total = amount * _UNIT_MULTIPLIERS.get(unit, 1)

        comparison_hint = None
        direction = match.group(1)
        if direction == "کمتر":
            comparison_hint = "<"
        elif direction == "بیشتر":
            comparison_hint = ">"

        phrases.append(
            NumericPhrase(
                raw_text=match.group(0).strip(),
                amount=total,
                comparison_hint=comparison_hint,
            )
        )
    return phrases
