"""Plan and execute table-level incremental semantic synchronization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from backend.config import get_settings
from backend.database.models import SchemaDiscoverySnapshot
from backend.database.discovery_service import schema_discovery_service
from backend.database.sync_service import schema_sync_service
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.benchmark_service import semantic_benchmark_service
from backend.semantic.suggestion_service import semantic_suggestion_service
from backend.value_index.service import value_index_service


@dataclass(frozen=True, slots=True)
class IncrementalChangeSet:
    added_tables: tuple[str, ...] = ()
    removed_tables: tuple[str, ...] = ()
    structurally_changed_tables: tuple[str, ...] = ()
    value_changed_tables: tuple[str, ...] = ()
    unchanged_tables: tuple[str, ...] = ()
    relationships_changed: bool = False

    @property
    def changed_tables(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            *self.added_tables,
            *self.structurally_changed_tables,
            *self.value_changed_tables,
        )))

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_tables or self.removed_tables or self.relationships_changed)

    def as_dict(self) -> dict[str, object]:
        return {
            "added_tables": list(self.added_tables),
            "removed_tables": list(self.removed_tables),
            "structurally_changed_tables": list(self.structurally_changed_tables),
            "value_changed_tables": list(self.value_changed_tables),
            "unchanged_tables": list(self.unchanged_tables),
            "relationships_changed": self.relationships_changed,
            "changed_tables": list(self.changed_tables),
        }


class IncrementalSyncPlanner:
    """Compare snapshots using stable structural and value-level table digests."""

    @staticmethod
    def _digest(payload: object) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _structural_digest(self, table: object) -> str:
        payload = table.model_dump()
        payload.pop("row_count", None)
        payload.pop("sample_rows", None)
        for column in payload.get("columns", []):
            column.pop("sample_values", None)
        return self._digest(payload)

    def _value_digest(self, table: object) -> str:
        payload = {
            "row_count": table.row_count,
            "sample_rows": table.sample_rows,
            "sample_values": {
                column.name: [sample.model_dump() for sample in column.sample_values]
                for column in table.columns
            },
        }
        return self._digest(payload)

    def compare(
        self,
        previous: SchemaDiscoverySnapshot,
        current: SchemaDiscoverySnapshot,
    ) -> IncrementalChangeSet:
        old = {table.name: table for table in previous.tables}
        new = {table.name: table for table in current.tables}
        added = sorted(new.keys() - old.keys())
        removed = sorted(old.keys() - new.keys())
        structural: list[str] = []
        values: list[str] = []
        unchanged: list[str] = []
        for name in sorted(old.keys() & new.keys()):
            if self._structural_digest(old[name]) != self._structural_digest(new[name]):
                structural.append(name)
            elif self._value_digest(old[name]) != self._value_digest(new[name]):
                values.append(name)
            else:
                unchanged.append(name)
        relationships_changed = self._digest(
            [item.model_dump() for item in previous.relationships]
        ) != self._digest([item.model_dump() for item in current.relationships])
        return IncrementalChangeSet(
            added_tables=tuple(added),
            removed_tables=tuple(removed),
            structurally_changed_tables=tuple(structural),
            value_changed_tables=tuple(values),
            unchanged_tables=tuple(unchanged),
            relationships_changed=relationships_changed,
        )


class IncrementalAutoSyncService:
    """Update only changed table artifacts, then activate and quality-check."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.planner = IncrementalSyncPlanner()

    async def run(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
        min_pass_rate: float = 95.0,
        benchmark_limit: Optional[int] = None,
        force_activate: bool = False,
    ) -> dict[str, object]:
        tenant = tenant_id or self.settings.tenant_id
        previous = semantic_activation_service.load_discovery(tenant)
        current = schema_discovery_service.discover(
            tenant_id=tenant,
            schema_name=schema_name,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )
        changes = self.planner.compare(previous, current)
        if not changes.has_changes:
            return {
                "status": "skipped",
                "tenant_id": tenant,
                "source_fingerprint": current.fingerprint,
                "changes": changes.as_dict(),
                "message": "No table-level changes were detected.",
            }

        discovery_path = schema_discovery_service.save_snapshot(current)
        schema_sync = schema_sync_service.sync_schema(tenant)
        if schema_sync.status != "success":
            return {
                "status": "failed", "tenant_id": tenant,
                "source_fingerprint": current.fingerprint,
                "changes": changes.as_dict(),
                "message": "Validator schema synchronization failed.",
            }

        suggestions, suggestions_path = semantic_suggestion_service.sync_incremental(
            current,
            changed_tables=set(changes.changed_tables),
            removed_tables=set(changes.removed_tables),
        )
        aliases = {
            f"{table.name}.{column.name}": [column.name, column.display_name_fa, *column.aliases_fa]
            for table in suggestions.tables for column in table.columns
        }
        pii = {
            f"{table.name}.{column.name}"
            for table in suggestions.tables for column in table.columns if column.pii
        }
        value_index, value_index_path = value_index_service.sync_incremental(
            current,
            changed_tables=set(changes.changed_tables),
            removed_tables=set(changes.removed_tables),
            column_aliases=aliases,
            pii_columns=pii,
        )
        if self.settings.value_index_deep_enabled:
            try:
                value_index, _deep_stats = value_index_service.deep_refresh(
                    value_index, current
                )
                value_index_path = value_index_service.save(value_index)
            except Exception:
                pass  # deep refresh is best-effort; sampled index remains usable
        activation = semantic_activation_service.activate(tenant, force=force_activate)
        if activation.status == "blocked":
            return {
                "status": "blocked", "tenant_id": tenant,
                "source_fingerprint": current.fingerprint,
                "changes": changes.as_dict(),
                "activation": activation.model_dump(mode="json"),
                "message": "Incremental artifacts were built, but activation requires review.",
            }
        benchmark = await semantic_benchmark_service.run(
            tenant_id=tenant, min_pass_rate=min_pass_rate, limit=benchmark_limit,
        )
        return {
            "status": "ready" if benchmark.status == "passed" else "failed",
            "tenant_id": tenant,
            "source_fingerprint": current.fingerprint,
            "changes": changes.as_dict(),
            "artifacts": {
                "discovery": str(discovery_path),
                "suggestions": str(suggestions_path),
                "value_index": str(value_index_path),
                "value_entries": len(value_index.entries),
            },
            "activation": activation.model_dump(mode="json"),
            "benchmark": benchmark.model_dump(mode="json"),
            "message": "Changed tables were synchronized and validated incrementally.",
        }


incremental_sync_service = IncrementalAutoSyncService()
