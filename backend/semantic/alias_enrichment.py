"""LLM-assisted Persian alias enrichment (accuracy work #2).

For every safe, non-key column without good Persian coverage, ask the LOCAL
model for short synonyms a business user would type, merge them into the
semantic suggestion set, and cache results per schema fingerprint so repeated
lifecycles never re-prompt unchanged columns.

Safety/robustness rules:
- LLM is optional: disabled or unreachable -> deterministic aliases remain.
- PII / key / identifier-like columns are never enriched.
- Output is sanitized (length, character classes, dedupe, cap).
- Everything is cached in schema/tenants/{tenant}/alias_enrichment.json.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.semantic.models import SemanticSuggestionSet
from backend.services.llm_service import llm_service

_SENSITIVE_PARTS = {
    "national_id", "password", "secret", "token", "phone", "mobile",
    "email", "address", "first_name", "last_name", "full_name",
}

_PERSIAN_LETTER = re.compile(r"[\u0600-\u06EF]")
_ALLOWED_CHARS = re.compile(r"^[\u0600-\u06EF a-zA-Z0-9_\u200c]+$")
_MAX_ALIASES_PER_COLUMN = 10


class AliasEnrichmentService:
    def __init__(self) -> None:
        self.settings = llm_service.settings

    @property
    def _schema_root(self) -> Path:
        return Path(__file__).parent.parent.parent / "schema" / "tenants"

    def _cache_path(self, tenant_id: str) -> Path:
        return self._schema_root / tenant_id / "alias_enrichment.json"

    def _load_cache(self, tenant_id: str) -> Dict[str, Any]:
        path = Path(self._cache_path(tenant_id))
        if not path.exists():
            return {"fingerprint": "", "signatures": {}, "aliases": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"fingerprint": "", "signatures": {}, "aliases": {}}

    def _save_cache(self, tenant_id: str, cache: Dict[str, Any]) -> Path:
        path = Path(self._cache_path(tenant_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------

    @staticmethod
    def _column_signature(table_name: str, column) -> str:
        """Cache key: identity + type. Samples change too often to be useful."""
        return f"{table_name}.{column.name}.{column.data_type}"

    @staticmethod
    def _is_enrichable(column) -> bool:
        name = column.name.lower()
        if name in {"id", "uuid", "guid"} or name.endswith("_id"):
            return False
        if any(part in name for part in _SENSITIVE_PARTS):
            return False
        if getattr(column, "pii", False):
            return False
        if column.data_type not in {
            "character varying", "character", "text", "USER-DEFINED",
            "integer", "bigint", "numeric", "date",
            "timestamp without time zone", "boolean",
        }:
            return False
        return True

    @staticmethod
    def _sanitize(raw_values: List[Any]) -> List[str]:
        cleaned: List[str] = []
        seen = set()
        for item in raw_values:
            if not isinstance(item, str):
                continue
            alias = re.sub(r"\s+", " ", item.strip().strip("«»\"'`"))
            if not 2 <= len(alias) <= 40:
                continue
            if not _ALLOWED_CHARS.match(alias):
                continue
            has_persian = bool(_PERSIAN_LETTER.search(alias))
            has_latin = bool(re.search(r"[A-Za-z]", alias))
            # Prompt asks for Persian-only; reject mixed-script artifacts like
            # «پرORITY» and pure-Latin echoes of column names.
            if not has_persian or has_latin:
                continue
            key = alias.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(alias)
            if len(cleaned) >= 6:
                break
        return cleaned

    def _build_prompt(self, table_name: str, display_fa: str, column) -> str:
        raw_samples = getattr(column, "sample_values", None) or []
        sample_list = ", ".join(
            repr(str(sample.value)) for sample in raw_samples[:6]
            if getattr(sample, "value", None)
        ) or "بدون نمونه"
        return (
            "You are a bilingual data analyst. A PostgreSQL table has this column:\n"
            f"table: {table_name} ({display_fa})\n"
            f"column: {column.name} ({column.data_type})\n"
            f"sample values: {sample_list}\n\n"
            "Suggest 4 to 6 SHORT Persian synonyms/phrases a non-technical Iranian "
            "business user might type when referring to this column in a question.\n"
            "Rules:\n"
            "- Persian only (Farsi script), no English words, no SQL\n"
            "- each 2-30 characters, no explanations\n"
            '- Respond with ONLY a JSON array of strings like ["مثال۱", "مثال۲"]'
        )

    @staticmethod
    def _parse_aliases(response: str) -> List[str]:
        if not response:
            return []
        match = re.search(r"\[.*\]", response, flags=re.DOTALL)
        candidate_text = match.group(0) if match else ""
        parsed: Any = None
        if candidate_text:
            try:
                parsed = json.loads(candidate_text)
            except Exception:
                parsed = None
        if not isinstance(parsed, list):
            parsed = re.findall(r"[«\"']([^«»\"']{2,40})[»\"']", response)
        return AliasEnrichmentService._sanitize(parsed)

    # ------------------------------------------------------------------

    async def enrich_suggestions(
        self,
        tenant_id: str,
        suggestions: SemanticSuggestionSet,
        *,
        max_prompts: Optional[int] = None,
    ) -> tuple[SemanticSuggestionSet, Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "enabled": True,
            "prompted": 0,
            "cache_hits": 0,
            "columns_enriched": 0,
            "aliases_added": 0,
            "failed": 0,
        }
        if not self.settings.llm_enabled:
            stats["enabled"] = False
            stats["reason"] = "llm_disabled"
            return suggestions, stats

        connected = await llm_service.is_connected()
        if not connected:
            stats["enabled"] = False
            stats["reason"] = "llm_unreachable"
            return suggestions, stats

        budget = max_prompts if max_prompts is not None else int(
            self.settings.alias_max_columns_per_run
        )

        cache = self._load_cache(tenant_id)
        if cache.get("fingerprint") != suggestions.source_fingerprint:
            cache["fingerprint"] = suggestions.source_fingerprint
            cache.setdefault("signatures", {})
            cache.setdefault("aliases", {})

        signatures: Dict[str, str] = cache.setdefault("signatures", {})
        stored: Dict[str, List[str]] = cache.setdefault("aliases", {})

        pending: List[tuple[Any, Any, str]] = []  # (table_suggestion, column_suggestion, key)
        for table in suggestions.tables:
            display_fa = getattr(table, "display_name_fa", "") or table.name
            for column in table.columns:
                key = f"{table.name}.{column.name}"
                signature = self._column_signature(table.name, column)
                if signatures.get(key) == signature and stored.get(key):
                    continue
                if not self._is_enrichable(column):
                    continue
                pending.append((table, column, key))
                signatures[key] = signature  # remember even if prompt fails this run

        prompted = 0
        failed = 0
        cache_hits = sum(1 for _, _, key in pending if stored.get(key))
        for table, column, key in pending:
            if prompted >= budget:
                break
            display_fa = getattr(table, "display_name_fa", "") or table.name
            prompt = self._build_prompt(table.name, display_fa, column)
            prompted += 1
            try:
                response = await llm_service.chat(prompt)
            except Exception:
                failed += 1
                continue
            aliases = self._parse_aliases(response)
            if not aliases:
                failed += 1
                continue
            stored[key] = aliases

        applied_columns = 0
        added_total = 0
        for table in suggestions.tables:
            for column in table.columns:
                key = f"{table.name}.{column.name}"
                # Re-sanitize on every apply: older cache entries written
                # before stricter rules get cleaned without re-prompting.
                extra = self._sanitize(stored.get(key) or [])
                if not extra:
                    continue
                merged = list(column.aliases_fa)
                before = len(merged)
                for alias in extra:
                    if alias not in merged and len(merged) < _MAX_ALIASES_PER_COLUMN:
                        merged.append(alias)
                if len(merged) > before:
                    column.aliases_fa = merged
                    added_total += len(merged) - before
                    applied_columns += 1

        stats.update(
            prompted=prompted,
            cache_hits=cache_hits,
            columns_enriched=applied_columns,
            aliases_added=added_total,
            failed=failed,
        )
        cache["saved_at"] = time.time()
        self._save_cache(tenant_id, cache)
        return suggestions, stats


alias_enrichment_service = AliasEnrichmentService()
