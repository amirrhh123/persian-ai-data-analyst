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
        from backend.config import get_settings

        self.settings = get_settings()
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
        if qualified in pii_columns or self._contains_part(
            column.name, _SENSITIVE_COLUMN_PARTS
        ):
            return "sensitive_column"
        if self._contains_part(column.name, _IDENTIFIER_COLUMN_PARTS):
            return "identifier_like_column"
        if column.name.endswith("_id"):
            return "relationship_identifier"
        if column.is_unique:
            return "unique_column"
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

    # ------------------------------------------------------------------
    # Fuzzy matching helpers (generic grounding accuracy)
    # ------------------------------------------------------------------

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token for token in text.split() if token]

    @staticmethod
    def _strip_plural(token: str) -> str:
        """Persian plural tolerance: «کارمندان» -> «کارمند», «مدیرها» -> «مدیر»."""
        for suffix in ("ها", "ان"):
            if len(token) > 3 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        if a == b:
            return 0
        if not a or not b:
            return max(len(a), len(b))
        previous = list(range(len(b) + 1))
        for i, char_a in enumerate(a, start=1):
            current = [i]
            for j, char_b in enumerate(b, start=1):
                cost = 0 if char_a == char_b else 1
                current.append(
                    min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
                )
            previous = current
        return previous[-1]

    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        distance = self._levenshtein(a, b)
        return 1.0 - (distance / max(len(a), len(b)))

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
        """Find database values mentioned in a question (exact, then fuzzy)."""
        active_index = index or (self.load(tenant_id) if tenant_id else None)
        if active_index is None or limit <= 0:
            return []
        normalized_question = self.normalize(question)
        matches: list[ValueIndexMatch] = []
        matched_keys: set[tuple[str, str, str]] = set()

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
                    match_kind="exact",
                )
            )
            matched_keys.add((entry.table, entry.column, entry.normalized_value))

        if self.settings.value_index_fuzzy_enabled:
            matches.extend(
                self._fuzzy_matches(
                    normalized_question,
                    active_index,
                    table=table,
                    columns=columns,
                    exclude=matched_keys,
                )
            )

        kind_rank = {"exact": 2, "token": 1, "fuzzy": 0}
        return sorted(
            matches,
            key=lambda match: (
                match.score,
                match.label_matched,  # label evidence breaks score ties
                kind_rank.get(match.match_kind, 0),
                len(self.normalize(match.value)),
                match.count,
                match.table,
                match.column,
            ),
            reverse=True,
        )[:limit]

    def _iter_candidate_entries(
        self,
        index: ValueIndexSnapshot,
        *,
        table: str | None,
        columns: set[str] | None,
        exclude: set[tuple[str, str, str]],
    ):
        for entry in index.entries:
            if table and entry.table != table:
                continue
            if columns is not None and entry.column not in columns:
                continue
            if (entry.table, entry.column, entry.normalized_value) in exclude:
                continue
            yield entry

    def _fuzzy_matches(
        self,
        normalized_question: str,
        index: ValueIndexSnapshot,
        *,
        table: str | None,
        columns: set[str] | None,
        exclude: set[tuple[str, str, str]],
    ) -> list[ValueIndexMatch]:
        question_tokens = [self._strip_plural(t) for t in self._tokens(normalized_question)]
        if len(question_tokens) < 1:
            return []
        min_similarity = float(self.settings.value_index_fuzzy_min_similarity)
        results: list[ValueIndexMatch] = []

        for entry in self._iter_candidate_entries(index, table=table, columns=columns, exclude=exclude):
            value_tokens = [
                self._strip_plural(t) for t in self._tokens(entry.normalized_value)
            ]
            if not value_tokens or any(len(t) < 2 for t in value_tokens):
                continue
            value_joined = " ".join(value_tokens)
            if len(value_joined) < 3:
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

            # Tier 1 — token subset: every value token appears somewhere in the
            # question (order-free). Catches reordering plus extra words.
            remaining = list(question_tokens)
            ok = True
            for token in value_tokens:
                if token in remaining:
                    remaining.remove(token)
                else:
                    ok = False
                    break
            if ok:
                score = 0.45 + (0.15 * length_score) + (0.08 * frequency_score)
                if matched_label:
                    score += 0.10
                results.append(
                    ValueIndexMatch(
                        table=entry.table,
                        column=entry.column,
                        value=entry.value,
                        count=entry.count,
                        score=round(min(0.95, score), 4),
                        label_matched=matched_label is not None,
                        matched_label=matched_label,
                        match_kind="token",
                    )
                )
                continue

            # Tier 2 — near-duplicate window: some consecutive span of question
            # tokens is one edit away from the value (typos, partial words).
            window_sizes = {len(value_tokens), len(value_tokens) + 1}
            best_similarity = 0.0
            for size in window_sizes:
                if size < 1 or size > len(question_tokens):
                    continue
                for start in range(0, len(question_tokens) - size + 1):
                    window = " ".join(question_tokens[start : start + size])
                    similarity = self._similarity(value_joined, window)
                    if similarity > best_similarity:
                        best_similarity = similarity
            if best_similarity >= min_similarity:
                score = 0.40 + (0.12 * length_score) + (0.07 * frequency_score)
                if matched_label:
                    score += 0.08
                results.append(
                    ValueIndexMatch(
                        table=entry.table,
                        column=entry.column,
                        value=entry.value,
                        count=entry.count,
                        score=round(min(0.90, score), 4),
                        label_matched=matched_label is not None,
                        matched_label=matched_label,
                        match_kind="fuzzy",
                    )
                )

        return results

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

    def sync_incremental(
        self,
        discovery: SchemaDiscoverySnapshot,
        *,
        changed_tables: set[str],
        removed_tables: set[str],
        column_aliases: Mapping[str, list[str]] | None = None,
        pii_columns: set[str] | None = None,
    ) -> tuple[ValueIndexSnapshot, Path]:
        """Replace index slices for changed tables and discard removed tables."""
        previous = self.load(discovery.tenant_id)
        refresh_tables = changed_tables | {
            table.name for table in discovery.tables
            if previous is None
        }
        partial_snapshot = discovery.model_copy(
            update={
                "tables": [table for table in discovery.tables if table.name in refresh_tables]
            }
        )
        partial = self.build(
            partial_snapshot,
            column_aliases=column_aliases,
            pii_columns=pii_columns,
        )
        retained_entries = [] if previous is None else [
            entry for entry in previous.entries
            if entry.table not in refresh_tables and entry.table not in removed_tables
        ]
        retained_excluded = {} if previous is None else {
            key: value for key, value in previous.excluded_columns.items()
            if key.split(".", 1)[0] not in refresh_tables | removed_tables
        }
        combined = ValueIndexSnapshot(
            tenant_id=discovery.tenant_id,
            source_fingerprint=discovery.fingerprint,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            entries=sorted(
                [*retained_entries, *partial.entries],
                key=lambda entry: (entry.table, entry.column, -entry.count, entry.normalized_value),
            ),
            excluded_columns={**retained_excluded, **partial.excluded_columns},
        )
        return combined, self.save(combined)

    # ------------------------------------------------------------------
    # Deep refresh: full DISTINCT scans for low-cardinality columns
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_ident(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _deep_eligible_columns(
        self,
        discovery: SchemaDiscoverySnapshot,
        index: ValueIndexSnapshot,
    ) -> list[tuple[DiscoveredTableInfo, DiscoveredColumnInfo]]:
        """Safety-cleared text columns ordered smallest-table-first.

        Unlike sample-based indexing, the sample-cardinality heuristics do NOT
        apply here: replacing weak samples is precisely this pass's purpose.
        Only hard safety rules (PK / unique / sensitive / identifier-like /
        unsupported types) exclude a column.
        """
        pii: set[str] = set()
        eligible: list[tuple[DiscoveredTableInfo, DiscoveredColumnInfo]] = []
        for table in discovery.tables:
            for column in table.columns:
                if column.is_primary_key:
                    continue
                qualified = f"{table.name}.{column.name}"
                if (
                    qualified in pii
                    or self._contains_part(column.name, _SENSITIVE_COLUMN_PARTS)
                ):
                    continue
                if self._contains_part(column.name, _IDENTIFIER_COLUMN_PARTS):
                    continue
                if column.name.endswith("_id"):
                    continue
                if column.is_unique:
                    continue
                if column.data_type not in {
                    "character varying", "character", "text", "USER-DEFINED",
                }:
                    continue
                eligible.append((table, column))
        eligible.sort(key=lambda pair: (pair[0].row_count or 0, pair[0].name, pair[1].name))
        return eligible

    def deep_refresh(
        self,
        index: ValueIndexSnapshot,
        discovery: SchemaDiscoverySnapshot,
        *,
        executor=None,
    ) -> tuple[ValueIndexSnapshot, dict[str, int]]:
        """Replace sampled slices with full DISTINCT scans where affordable.

        For every safety-cleared text column we run
            SELECT col, COUNT(*) FROM table GROUP BY col ORDER BY 2 DESC LIMIT N+1
        Columns whose distinct count exceeds the cap stay sample-indexed and
        are flagged. Read-only by construction; identifiers come from
        information_schema and are double-quoted.
        """
        from backend.database.models import (
            DiscoveredColumnInfo,
            DiscoveredTableInfo,
        )  # noqa: F401  (type hints + public API symmetry)

        if executor is None:
            from backend.database.connection import db_connection

            def executor(sql: str):
                return db_connection.execute_query(sql).all()

        max_distinct = int(self.settings.value_index_max_distinct)
        max_values = int(self.settings.value_index_max_values_per_column)
        budget = int(self.settings.value_index_deep_column_budget)

        alias_map: dict[str, list[str]] = {}
        for entry in index.entries:
            qualified = f"{entry.table}.{entry.column}"
            bucket = alias_map.setdefault(qualified, [])
            for alias in entry.column_aliases:
                if alias not in bucket:
                    bucket.append(alias)

        refreshed_keys: set[tuple[str, str]] = set()
        new_entries: list[ValueIndexEntry] = []
        stats = {"scanned": 0, "indexed": 0, "skipped_cardinality": 0, "errors": 0}
        deep_excluded: dict[str, str] = {}

        for table, column in self._deep_eligible_columns(discovery, index):
            if stats["scanned"] >= budget:
                break
            sql = (
                f"SELECT {self._quote_ident(column.name)}, COUNT(*) AS cnt "
                f"FROM {self._quote_ident(table.name)} "
                f"GROUP BY {self._quote_ident(column.name)} "
                f"ORDER BY cnt DESC "
                f"LIMIT {max_distinct + 1}"
            )
            stats["scanned"] += 1
            try:
                rows = executor(sql) or []
            except Exception:
                stats["errors"] += 1
                continue

            if len(rows) > max_distinct:
                stats["skipped_cardinality"] += 1
                deep_excluded[f"{table.name}.{column.name}"] = "deep_high_cardinality"
                continue

            qualified = f"{table.name}.{column.name}"
            aliases = alias_map.get(qualified, [])
            kept = 0
            seen: set[str] = set()
            for row in rows:
                if kept >= max_values:
                    break
                value = row[0]
                count = row[1] if len(row) > 1 else 0
                if value is None:
                    continue
                text_value = str(value).strip()
                normalized = self.normalize(text_value)
                if not normalized or len(normalized) > 120 or normalized in seen:
                    continue
                seen.add(normalized)
                new_entries.append(
                    ValueIndexEntry(
                        table=table.name,
                        column=column.name,
                        value=text_value,
                        normalized_value=normalized,
                        count=int(count or 0),
                        column_aliases=list(aliases),
                    )
                )
                kept += 1
            refreshed_keys.add((table.name, column.name))
            stats["indexed"] += 1

        retained = [
            entry
            for entry in index.entries
            if (entry.table, entry.column) not in refreshed_keys
        ]
        excluded = {**index.excluded_columns, **deep_excluded}
        merged = ValueIndexSnapshot(
            tenant_id=index.tenant_id,
            source_fingerprint=index.source_fingerprint,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            entries=sorted(
                [*retained, *new_entries],
                key=lambda entry: (entry.table, entry.column, -entry.count, entry.normalized_value),
            ),
            excluded_columns=excluded,
        )
        return merged, stats


value_index_service = ValueIndexService()
