from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError


class StructuredSQLResponse(BaseModel):
    sql: str
    explanation: str
    confidence: float


def strip_markdown_fences(text: str) -> str:
    cleaned = re.sub(r"```(?:json|sql)?", "", text, flags=re.IGNORECASE)
    return cleaned.replace("```", "").strip()


def extract_json_object(text: str) -> str:
    cleaned = strip_markdown_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("خروجی مدل شامل JSON معتبر نیست.")
    return cleaned[start : end + 1]


def ensure_single_select(sql: str) -> str:
    clean_sql = sql.strip().rstrip(";").strip()
    if not re.match(r"^select\b", clean_sql, flags=re.IGNORECASE):
        raise ValueError("SQL باید با SELECT شروع شود.")
    if re.search(r";\s*\S", sql):
        raise ValueError("SQL نباید چند دستور داشته باشد.")
    return clean_sql


def parse_structured_sql_response(raw_response: str) -> StructuredSQLResponse:
    try:
        payload = json.loads(extract_json_object(raw_response))
        parsed = StructuredSQLResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ValueError(f"خروجی ساختاریافته مدل نامعتبر است: {exc}") from exc

    parsed.sql = ensure_single_select(parsed.sql)
    return parsed

