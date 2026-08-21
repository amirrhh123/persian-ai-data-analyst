"""Request-scoped semantic snapshot provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.semantic.compiler import CompiledSemanticRules, semantic_compiler
from backend.semantic.context_index import SemanticContextIndex, semantic_context_index_service
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog


@dataclass(frozen=True, slots=True)
class SemanticSnapshot:
    """One immutable catalog version shared by every stage of a request."""

    tenant_id: str
    catalog: SemanticCatalog
    compiled: CompiledSemanticRules
    context_index: SemanticContextIndex
    captured_at: str

    @property
    def version(self) -> int:
        return self.catalog.version


class SemanticSnapshotProvider:
    def capture(self, tenant_id: str) -> SemanticSnapshot:
        catalog = load_tenant_semantic_catalog(tenant_id)
        context_index, _ = semantic_context_index_service.get_or_build(tenant_id, catalog)
        return SemanticSnapshot(
            tenant_id=tenant_id,
            catalog=catalog,
            compiled=semantic_compiler.compile(catalog),
            context_index=context_index,
            captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )


semantic_snapshot_provider = SemanticSnapshotProvider()
