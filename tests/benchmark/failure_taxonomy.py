"""Failure taxonomy and normalization helpers for the SQL quality benchmark.

The 13 categories mirror LANGGRAPH_SQL_QUALITY_ROADMAP.md. Stage detection maps
the first failing pipeline trace step (plus validation error messages) to a
taxonomy category so failed cases report *where* the pipeline broke.
"""

from __future__ import annotations

import re
from typing import Any

CATEGORIES: list[str] = [
    "intent",
    "entity",
    "table",
    "column",
    "filter",
    "value",
    "join",
    "aggregate",
    "grouping",
    "ranking",
    "result_shape",
    "safety",
    "answer",
]

# Ordered earliest-to-latest pipeline stages as emitted by PipelineTracer.
STAGE_ORDER: list[str] = [
    "safety_intent_check",
    "multi_intent_detection",
    "ambiguity_detection",
    "group_retrieval",
    "report_retrieval",
    "intent_extraction",
    "semantic_resolution",
    "intent_normalization",
    "unsupported_detection",
    "sql_planning",
    "aggregate_safety",
    "sql_generation",
    "sql_repair",
    "sql_validation",
    "sql_execution",
    "result_shape_validation",
    "answer_generation",
]

# Default category hint per stage when no stronger signal exists.
STAGE_CATEGORY_HINTS: dict[str, str] = {
    "safety_intent_check": "safety",
    "multi_intent_detection": "intent",
    "ambiguity_detection": "safety",
    "group_retrieval": "entity",
    "report_retrieval": "table",
    "intent_extraction": "intent",
    "semantic_resolution": "table",
    "intent_normalization": "intent",
    "unsupported_detection": "safety",
    "sql_planning": "join",
    "aggregate_safety": "aggregate",
    "sql_generation": "column",
    "sql_repair": "column",
    "sql_validation": "filter",
    "sql_execution": "safety",
    "result_shape_validation": "result_shape",
    "answer_generation": "answer",
}

# Persian validator/execution message keywords override stage hints because they
# pinpoint the true failure dimension better than the stage name alone.
_MESSAGE_CATEGORY_RULES: list[tuple[str, str]] = [
    ("فیلتر ضروری", "filter"),
    ("required filter", "filter"),
    ("ستون درخواستی", "column"),
    ("requested column", "column"),
    ("جدول", "table"),
    ("table not allowed", "safety"),
    ("ممنوعه", "safety"),
]

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ZWNJ = "\u200c"


def normalize_digits(text: str) -> str:
    """Map Persian/Arabic-Indic digits to ASCII digits."""
    return text.translate(_PERSIAN_DIGITS)


def normalize_text(value: Any) -> str:
    """Normalize text for comparisons: digits, ZWNJ, quotes, whitespace, case."""
    if value is None:
        return ""
    text = normalize_digits(str(value))
    text = text.replace(_ZWNJ, "")
    for quote in ("'", '"', "`", "«", "»"):
        text = text.replace(quote, "")
    text = re.sub(r"\s+", " ", text.strip().lower())
    return text


def normalize_identifier(value: Any) -> str:
    """Normalize a SQL identifier or identifier fragment."""
    text = normalize_text(value)
    return text.replace(" ", "")


def first_failing_stage(response: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first failing trace step with its error details."""
    steps = (response.get("trace") or {}).get("steps") or []
    by_name: dict[str, dict[str, Any]] = {}
    for step in steps:
        if isinstance(step, dict) and step.get("name"):
            by_name.setdefault(str(step["name"]), step)

    detail_by_stage: dict[str, list[str]] = {}
    for item in response.get("error_details") or []:
        if isinstance(item, dict) and item.get("stage"):
            detail_by_stage.setdefault(str(item["stage"]), []).append(
                str(item.get("message") or item.get("code") or "")
            )

    for stage in STAGE_ORDER:
        step = by_name.get(stage)
        status = (step or {}).get("status")
        details = detail_by_stage.get(stage, [])
        hard_errors = [
            item.get("message")
            for item in response.get("error_details") or []
            if isinstance(item, dict)
            and item.get("stage") == stage
            and item.get("severity") == "error"
        ]
        if status == "error" or hard_errors:
            messages = [str(m) for m in (hard_errors or details)]
            return {"stage": stage, "messages": messages}
    return None


def suggest_category(response: dict[str, Any], default: str | None = None) -> str:
    """Infer the most likely taxonomy category from the failing stage + messages."""
    failure = first_failing_stage(response)
    if not failure:
        return default or "answer"

    messages = " | ".join(failure["messages"]).lower()
    for keyword, category in _MESSAGE_CATEGORY_RULES:
        if keyword.lower() in messages:
            return category
    return STAGE_CATEGORY_HINTS.get(failure["stage"], default or "answer")


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise ValueError(
            f"Unknown category {category!r}. Valid categories: {', '.join(CATEGORIES)}"
        )
    return category
