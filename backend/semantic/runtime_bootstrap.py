"""Build a semantic catalog directly from the live database.

This is the portable path: a deployment may start with no checked-in
``knowledge`` or ``schema`` files.  Discovery is fingerprinted and the
resulting catalog is cached locally for fast subsequent requests.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.config import get_settings
from backend.database.discovery_service import schema_discovery_service
from backend.database.models import SchemaDiscoverySnapshot
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticJoin, SemanticMetric, SemanticRule, SemanticTable
from backend.semantic.suggestion_service import semantic_suggestion_service


class RuntimeSemanticBootstrap:
    def __init__(self) -> None:
        self.root = Path(__file__).parent.parent.parent / ".runtime" / "semantic-cache"

    def _path(self, tenant_id: str, fingerprint: str) -> Path:
        return self.root / tenant_id / f"{fingerprint}.json"

    def _catalog(self, suggestions) -> SemanticCatalog:
        tables = [
            SemanticTable(
                name=t.name, entity=t.entity, description=t.description_fa,
                aliases=t.aliases_fa, primary_key=t.primary_key,
                default_display_columns=t.default_display_columns,
                profile_columns=t.profile_columns,
                columns=[SemanticColumn(name=c.name, data_type=c.data_type,
                    description=c.description_fa, aliases=c.aliases_fa,
                    value_type=c.value_type, pii=c.pii) for c in t.columns],
            ) for t in suggestions.tables
        ]
        joins = [SemanticJoin(from_table=j.from_table, from_column=j.from_column,
            to_table=j.to_table, to_column=j.to_column,
            description=j.description_fa, cardinality=j.cardinality) for j in suggestions.joins]
        rules = [SemanticRule(name=r.name, description=r.description_fa, applies_to=r.applies_to)
                 for r in suggestions.rules]
        for term in suggestions.business_terms:
            rules.append(SemanticRule(name=f"business_term_{term.maps_to.replace('.', '_')}",
                description=f"{term.term_fa}: {term.description_fa}", applies_to=[term.maps_to]))
        for mapping in suggestions.value_mappings:
            rules.append(SemanticRule(name=f"value_mapping_{mapping.column.replace('.', '_')}_{mapping.value}",
                description=f"{mapping.term_fa}: {mapping.description_fa}", applies_to=[mapping.column]))
        return SemanticCatalog(version=suggestions.version, language=suggestions.language,
                               tables=tables, joins=joins, rules=rules,
                               value_mappings=[mapping.model_dump() for mapping in suggestions.value_mappings],
                               business_terms=[term.model_dump() for term in suggestions.business_terms],
                               metrics=[SemanticMetric(name=m.name, table=m.table,
                                   expression=m.expression, aggregation=m.aggregation,
                                   description=m.description_fa, aliases=m.aliases_fa)
                                   for m in suggestions.metrics])

    def load(self, tenant_id: str, discovery: SchemaDiscoverySnapshot | None = None) -> SemanticCatalog:
        # Avoid a full information_schema/sample scan on every request.
        # Lifecycle/discovery endpoints can force a refresh by passing a snapshot.
        if discovery is None:
            ttl = max(0, int(get_settings().runtime_semantic_cache_ttl_seconds))
            tenant_dir = self.root / tenant_id
            if ttl and tenant_dir.exists():
                recent = sorted(tenant_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if recent and time.time() - recent[0].stat().st_mtime < ttl:
                    return SemanticCatalog.model_validate(json.loads(recent[0].read_text(encoding="utf-8")))
        snapshot = discovery or schema_discovery_service.discover(tenant_id=tenant_id)
        path = self._path(tenant_id, snapshot.fingerprint)
        if path.exists():
            return SemanticCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))
        suggestions = semantic_suggestion_service.generate(tenant_id, discovery=snapshot)
        catalog = self._catalog(suggestions)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return catalog

    def refresh(self, tenant_id: str) -> tuple[SemanticCatalog, bool, SchemaDiscoverySnapshot]:
        """Discover the live database and rebuild semantics only when needed."""
        snapshot = schema_discovery_service.discover(tenant_id=tenant_id)
        path = self._path(tenant_id, snapshot.fingerprint)
        if path.exists():
            return SemanticCatalog.model_validate(json.loads(path.read_text(encoding="utf-8"))), False, snapshot
        return self.load(tenant_id, discovery=snapshot), True, snapshot


runtime_semantic_bootstrap = RuntimeSemanticBootstrap()
