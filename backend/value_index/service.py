"""Build, persist, and query a safe generic database value index."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from backend.database.models import (
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.value_index.models import (
    ValueIndexEntry,
    ValueIndexMatch,
    ValueIndexSnapshot,
)


_CHAR_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "‌": " ",
    }
)
_SENSITIVE_COLUMN_PARTS = {
    "national_id",
    "phone",
    "mobile",
    "email",
    "password",
    "secret",
    "token",
    "first_name",
    "last_name",
    "full_name",
    "address",
}
_IDENTIFIER_COLUMN_PARTS = {"tracking_code", "serial", "uuid", "guid"}
_SUPPORTED_TYPES = {
    "text",
    "character varying",
    "character",
    "boolean",
    "integer",
    "smallint",
    "USER-DEFINED",
}


class ValueIndexService:
    """Manage a bounded, file-backed index of safe categorical values."""

    def __init__(self, schema_root: Path | None = None) -> None:
        """Initialize the service.

        Args:
            schema_root: Root containing tenant schema artifacts.
        """
        self.schema_root = schema_root or (
            Path(__file__).parent.parent.parent / "schema"
        )

    @staticmethod
    def normalize(value: str) -> str:
        """Normalize Persian variants, digits, spacing, and separators."""
        normalized = value.translate(_CHAR_TRANSLATION).casefold()
        normalized = re.sub(r"[_\-/]+", " ", normalized)
        return " ".join(normalized.split())

    def index_path(self, tenant_id: str) -> Path:
        """Return the tenant's value-index artifact path."""
        return self.schema_root / "tenants" / tenant_id / "value_index.json"

    @staticmethod
    def _contains_part(column_name: str, parts: Iterable[str]) -> bool:
        lowered = column_name.casefold()
        return any(part in lowered for part in parts)

    def _exclusion_reason(
        self,
        table: DiscoveredTableInfo,
        column: DiscoveredColumnInfo,
        pii_columns: set[str],
    ) -> str | None:
        """Return why a column is unsafe or unsuitable for value indexing."""
        qualified = f"{table.name}.{column.name}"
        if column.is_primary_key:
            return "primary_key"
        if column.is_unique:
            return "unique_column"
        if column.name.endswith("_id"):
            return "relationship_identifier"
        if qualified in pii_columns or self._contains_part(
            column.name, _SENSITIVE_COLUMN_PARTS
        ):
            return "sensitive_column"
        if self._contains_part(column.name, _IDENTIFIER_COLUMN_PARTS):
            return "identifier_like_column"
        if column.data_type not in _SUPPORTED_TYPES:
            return "unsupported_type"
        samples = [sample for sample in column.sample_values if sample.value is not None]
        if not samples:
            return "no_sample_values"
        if table.row_count > len(samples) and all(sample.count <= 1 for sample in samples):
            return "high_cardinality_samples"
        return None

    def build(
        self,
        discovery: SchemaDiscoverySnapshot,
        *,
        column_aliases: Mapping[str, list[str]] | None = None,
        pii_columns: set[str] | None = None,
    ) -> ValueIndexSnapshot:
        """Build a safe index from database discovery samples."""
        aliases = column_aliases or {}
        pii = pii_columns or set()
        entries: list[ValueIndexEntry] = []
        excluded: dict[str, str] = {}

        for table in discovery.tables:
            for column in table.columns:
                qualified = f"{table.name}.{column.name}"
                reason = self._exclusion_reason(table, column, pii)
                if reason:
                    excluded[qualified] = reason
                    continue
                seen: set[str] = set()
                for sample in column.sample_values:
                    value = (sample.value or "").strip()
                    normalized = self.normalize(value)
                    if not normalized or len(normalized) > 120 or normalized in seen:
                        continue
                    seen.add(normalized)
                    entries.append(
                        ValueIndexEntry(
                            table=table.name,
                            column=column.name,
                            value=value,
                            normalized_value=normalized,
                            count=max(0, sample.count),
                            column_aliases=list(aliases.get(qualified, [])),
                        )
                    )

        entries.sort(
            key=lambda entry: (
                entry.table,
                entry.column,
                -entry.count,
                entry.normalized_value,
            )
        )
        return ValueIndexSnapshot(
            tenant_id=discovery.tenant_id,
            source_fingerprint=discovery.fingerprint,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            entries=entries,
            excluded_columns=excluded,
        )

    def save(self, index: ValueIndexSnapshot) -> Path:
        """Persist a value index atomically enough for local lifecycle use."""
        path = self.index_path(index.tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(index.model_dump(), file, ensure_ascii=False, indent=2)
        return path

    def load(self, tenant_id: str) -> ValueIndexSnapshot | None:
        """Load a tenant value index if it exists and is valid."""
        path = self.index_path(tenant_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            return ValueIndexSnapshot.model_validate(json.load(file))

    @staticmethod
    def _phrase_present(question: str, phrase: str) -> bool:
        """Check a whole normalized phrase boundary in a question."""
        return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", question))

    def search(
        self,
        question: str,
        *,
        tenant_id: str | None = None,
        index: ValueIndexSnapshot | None = None,
        table: str | None = None,
        columns: set[str] | None = None,
        limit: int = 20,
    ) -> list[ValueIndexMatch]:
        """Find exact database values mentioned in a natural-language question."""
        active_index = index or (self.load(tenant_id) if tenant_id else None)
        if active_index is None or limit <= 0:
            return []
        normalized_question = self.normalize(question)
        matches: list[ValueIndexMatch] = []

        for entry in active_index.entries:
            if table and entry.table != table:
                continue
            if columns is not None and entry.column not in columns:
                continue
            if not self._phrase_present(normalized_question, entry.normalized_value):
                continue

            matched_label = next(
                (
                    alias
                    for alias in entry.column_aliases
                    if self._phrase_present(normalized_question, self.normalize(alias))
                ),
                None,
            )
            length_score = min(1.0, len(entry.normalized_value) / 20.0)
            frequency_score = min(1.0, entry.count / 20.0)
            score = 0.55 + (0.2 * length_score) + (0.1 * frequency_score)
            if matched_label:
                score += 0.15
            matches.append(
                ValueIndexMatch(
                    table=entry.table,
                    column=entry.column,
                    value=entry.value,
                    count=entry.count,
                    score=round(min(1.0, score), 4),
                    label_matched=matched_label is not None,
                    matched_label=matched_label,
                )
            )

        return sorted(
            matches,
            key=lambda match: (
                match.score,
                len(self.normalize(match.value)),
                match.count,
                match.table,
                match.column,
            ),
            reverse=True,
        )[:limit]

    def sync(
        self,
        discovery: SchemaDiscoverySnapshot,
        *,
        column_aliases: Mapping[str, list[str]] | None = None,
        pii_columns: set[str] | None = None,
    ) -> tuple[ValueIndexSnapshot, Path]:
        """Build and persist a value index in one lifecycle operation."""
        index = self.build(
            discovery,
            column_aliases=column_aliases,
            pii_columns=pii_columns,
        )
        return index, self.save(index)


value_index_service = ValueIndexService()
