"""Versioned inverted index for fast semantic-context selection."""

from __future__ import annotations

import math
import re
import hashlib
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field

from backend.semantic.models import SemanticCatalog


_TRANSLATION = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "‌": " ",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def normalize_context_text(value: str) -> str:
    normalized = value.translate(_TRANSLATION).casefold()
    normalized = re.sub(r"[_\-/]+", " ", normalized)
    return " ".join(normalized.split())


@dataclass(frozen=True, slots=True)
class SemanticContextDocument:
    id: str
    kind: str
    text: str
    table: str = ""
    target: str = ""
    priority: float = 1.0
    related_tables: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticContextMatch:
    document: SemanticContextDocument
    score: float


@dataclass(slots=True)
class SemanticContextIndex:
    tenant_id: str
    version: int
    signature: str
    documents: tuple[SemanticContextDocument, ...]
    postings: dict[str, tuple[int, ...]] = field(default_factory=dict)
    document_tokens: tuple[Counter[str], ...] = ()
    document_frequency: dict[str, int] = field(default_factory=dict)

    def search(
        self,
        question: str,
        *,
        limit: int = 14,
        allowed_tables: set[str] | None = None,
    ) -> list[SemanticContextMatch]:
        """Return the highest-scoring context slices without scanning all text."""
        if limit <= 0:
            return []
        normalized = normalize_context_text(question)
        query_tokens = list(dict.fromkeys(_TOKEN_PATTERN.findall(normalized)))
        candidate_indexes: set[int] = set()
        for token in query_tokens:
            candidate_indexes.update(self.postings.get(token, ()))
        if allowed_tables:
            candidate_indexes.update(
                index for index, document in enumerate(self.documents)
                if document.table in allowed_tables and document.kind in {"table", "join"}
            )

        total_documents = max(1, len(self.documents))
        matches: list[SemanticContextMatch] = []
        for index in candidate_indexes:
            document = self.documents[index]
            if allowed_tables and document.related_tables:
                if not set(document.related_tables).issubset(allowed_tables):
                    continue
            elif allowed_tables and document.table and document.table not in allowed_tables:
                continue
            frequencies = self.document_tokens[index]
            score = 0.0
            for token in query_tokens:
                if frequencies[token] == 0:
                    continue
                inverse_frequency = math.log(
                    1 + total_documents / (1 + self.document_frequency.get(token, 0))
                )
                score += inverse_frequency * (1 + math.log(frequencies[token]))
            document_text = normalize_context_text(document.text)
            if normalized and normalized in document_text:
                score += 4.0
            elif any(
                len(token) >= 3 and re.search(rf"(?<!\w){re.escape(token)}(?!\w)", document_text)
                for token in query_tokens
            ):
                score += 0.5
            score *= document.priority
            if score <= 0 and allowed_tables and document.kind == "table" and document.table in allowed_tables:
                score = 0.2
            if score > 0:
                matches.append(SemanticContextMatch(document, round(score, 4)))
        return sorted(
            matches,
            key=lambda item: (item.score, item.document.priority, item.document.id),
            reverse=True,
        )[:limit]


class SemanticContextIndexService:
    """Build once per semantic version and retain a small tenant/version LRU."""

    def __init__(self, maximum_cached_versions: int = 8) -> None:
        self.maximum_cached_versions = maximum_cached_versions
        self._cache: OrderedDict[tuple[str, int, str], SemanticContextIndex] = OrderedDict()

    def get_or_build(
        self,
        tenant_id: str,
        catalog: SemanticCatalog,
    ) -> tuple[SemanticContextIndex, bool]:
        signature = hashlib.sha256(catalog.model_dump_json().encode("utf-8")).hexdigest()[:16]
        key = (tenant_id, catalog.version, signature)
        if key in self._cache:
            index = self._cache.pop(key)
            self._cache[key] = index
            return index, False
        index = self.build(tenant_id, catalog)
        self._cache[key] = index
        while len(self._cache) > self.maximum_cached_versions:
            self._cache.popitem(last=False)
        return index, True

    def build(self, tenant_id: str, catalog: SemanticCatalog) -> SemanticContextIndex:
        documents: list[SemanticContextDocument] = []
        for table in catalog.tables:
            documents.append(SemanticContextDocument(
                id=f"table:{table.name}", kind="table", table=table.name,
                target=table.name,
                text=f"{table.name} {table.description} {' '.join(table.aliases)}",
                priority=1.2,
            ))
            for column in table.columns:
                documents.append(SemanticContextDocument(
                    id=f"column:{table.name}.{column.name}", kind="column",
                    table=table.name, target=f"{table.name}.{column.name}",
                    text=f"{table.name}.{column.name} {column.description} {' '.join(column.aliases)} {column.value_type or ''}",
                    priority=1.15,
                ))
        for index, term in enumerate(catalog.business_terms):
            target = str(term.get("maps_to", ""))
            documents.append(SemanticContextDocument(
                id=f"term:{index}:{target}", kind="business_term",
                table=target.split(".", 1)[0], target=target,
                text=f"{term.get('term_fa', '')} {' '.join(term.get('aliases_fa', []))} {term.get('description_fa', '')} maps to {target}",
                priority=1.6,
            ))
        for index, mapping in enumerate(catalog.value_mappings):
            target = str(mapping.get("column", ""))
            documents.append(SemanticContextDocument(
                id=f"value:{index}:{target}", kind="value_mapping",
                table=target.split(".", 1)[0], target=target,
                text=f"{mapping.get('term_fa', '')} {' '.join(mapping.get('aliases_fa', []))} {mapping.get('description_fa', '')} {target} equals {mapping.get('value', '')}",
                priority=1.6,
            ))
        for metric in catalog.metrics:
            documents.append(SemanticContextDocument(
                id=f"metric:{metric.name}", kind="metric", table=metric.table,
                target=metric.name,
                text=f"{metric.name} {' '.join(metric.aliases)} {metric.description} {metric.aggregation or ''} {metric.expression}",
                priority=1.7,
            ))
        for index, rule in enumerate(catalog.rules):
            table = rule.applies_to[0].split(".", 1)[0] if rule.applies_to else ""
            documents.append(SemanticContextDocument(
                id=f"rule:{index}:{rule.name}", kind="rule", table=table,
                target=rule.name,
                text=f"{rule.name} {rule.description} {' '.join(rule.applies_to)}",
                priority=1.4,
                related_tables=tuple(dict.fromkeys(
                    item.split(".", 1)[0] for item in rule.applies_to if item
                )),
            ))
        for index, join in enumerate(catalog.joins):
            documents.append(SemanticContextDocument(
                id=f"join:{index}:{join.from_table}:{join.to_table}", kind="join",
                table=join.from_table, target=f"{join.from_table}->{join.to_table}",
                text=(f"{join.description} {join.from_table}.{join.from_column} "
                      f"joins {join.to_table}.{join.to_column} {join.cardinality}"),
                priority=1.35,
                related_tables=(join.from_table, join.to_table),
            ))

        postings: dict[str, list[int]] = defaultdict(list)
        token_counters: list[Counter[str]] = []
        document_frequency: Counter[str] = Counter()
        for document_index, document in enumerate(documents):
            counter = Counter(_TOKEN_PATTERN.findall(normalize_context_text(document.text)))
            token_counters.append(counter)
            for token in counter:
                postings[token].append(document_index)
                document_frequency[token] += 1
        return SemanticContextIndex(
            tenant_id=tenant_id,
            version=catalog.version,
            signature=hashlib.sha256(catalog.model_dump_json().encode("utf-8")).hexdigest()[:16],
            documents=tuple(documents),
            postings={token: tuple(indexes) for token, indexes in postings.items()},
            document_tokens=tuple(token_counters),
            document_frequency=dict(document_frequency),
        )

    def clear(self) -> None:
        self._cache.clear()


semantic_context_index_service = SemanticContextIndexService()
