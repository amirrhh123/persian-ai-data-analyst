from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import bindparam, text

from backend.database.connection import db_connection


SCHOOL_TYPE_PREFIXES = [
    "مدرسه",
    "دبیرستان",
    "دبستان",
    "هنرستان",
]


@dataclass
class SchoolResolution:
    resolved_name: str | None = None
    ambiguous: bool = False
    candidates: list[str] | None = None
    unavailable: bool = False


def normalize_school_query(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name or "").strip()
    normalized = re.sub(r"^(?:مدرسه|در مدرسه)\s+", "", normalized)
    return normalized


def school_name_variants(name: str) -> list[str]:
    normalized = normalize_school_query(name)
    variants = [normalized]
    if not any(normalized.startswith(prefix) for prefix in SCHOOL_TYPE_PREFIXES if prefix != "مدرسه"):
        variants.extend(f"{prefix} {normalized}" for prefix in SCHOOL_TYPE_PREFIXES if prefix != "مدرسه")
    return list(dict.fromkeys(item for item in variants if item))


def resolve_school_name(name: str) -> SchoolResolution:
    normalized = normalize_school_query(name)
    if not normalized:
        return SchoolResolution()

    try:
        exact_rows = db_connection.execute_query(
            "SELECT DISTINCT name FROM schools WHERE name = :name ORDER BY name LIMIT 5",
            {"name": normalized},
        ).mappings().all()
    except Exception:
        return SchoolResolution(unavailable=True)
    if len(exact_rows) == 1:
        return SchoolResolution(resolved_name=exact_rows[0]["name"])

    variants = school_name_variants(normalized)
    variant_sql = text("SELECT DISTINCT name FROM schools WHERE name IN :names ORDER BY name LIMIT 10").bindparams(
        bindparam("names", expanding=True)
    )
    try:
        variant_rows = db_connection.execute_query(
            variant_sql,
            {"names": variants},
        ).mappings().all()
    except Exception:
        return SchoolResolution(unavailable=True)
    if len(variant_rows) == 1:
        return SchoolResolution(resolved_name=variant_rows[0]["name"])
    if len(variant_rows) > 1:
        return SchoolResolution(ambiguous=True, candidates=[row["name"] for row in variant_rows])

    try:
        contains_rows = db_connection.execute_query(
            "SELECT DISTINCT name FROM schools WHERE name ILIKE :pattern ORDER BY name LIMIT 10",
            {"pattern": f"%{normalized}%"},
        ).mappings().all()
    except Exception:
        return SchoolResolution(unavailable=True)
    if len(contains_rows) == 1:
        return SchoolResolution(resolved_name=contains_rows[0]["name"])
    if len(contains_rows) > 1:
        return SchoolResolution(ambiguous=True, candidates=[row["name"] for row in contains_rows])

    return SchoolResolution()
