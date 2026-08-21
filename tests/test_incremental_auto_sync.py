"""Tests for table-level incremental synchronization."""

import pytest

from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.semantic.lifecycle_service import semantic_lifecycle_service
from backend.semantic.models import SemanticFreshnessResponse
from backend.sync.incremental_service import IncrementalSyncPlanner
from backend.value_index.models import ValueIndexEntry, ValueIndexSnapshot
from backend.value_index.service import ValueIndexService


def _table(
    name: str,
    *,
    column_name: str = "status",
    value: str = "active",
    row_count: int = 2,
) -> DiscoveredTableInfo:
    return DiscoveredTableInfo(
        name=name,
        row_count=row_count,
        columns=[DiscoveredColumnInfo(
            name=column_name,
            data_type="text",
            udt_name="text",
            sample_values=[ColumnSampleValue(value=value, count=row_count)],
        )],
    )


def _snapshot(fingerprint: str, *tables: DiscoveredTableInfo) -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="tenant",
        database_name="db",
        generated_at="2026-08-14T00:00:00",
        fingerprint=fingerprint,
        tables=list(tables),
    )


def test_planner_classifies_added_removed_structural_and_value_changes() -> None:
    previous = _snapshot(
        "old",
        _table("unchanged"),
        _table("removed"),
        _table("structural"),
        _table("values"),
    )
    current = _snapshot(
        "new",
        _table("unchanged"),
        _table("added"),
        _table("structural", column_name="state"),
        _table("values", value="inactive"),
    )

    changes = IncrementalSyncPlanner().compare(previous, current)

    assert changes.added_tables == ("added",)
    assert changes.removed_tables == ("removed",)
    assert changes.structurally_changed_tables == ("structural",)
    assert changes.value_changed_tables == ("values",)
    assert changes.unchanged_tables == ("unchanged",)
    assert changes.has_changes is True


def test_incremental_value_index_preserves_unchanged_and_removes_deleted(tmp_path) -> None:
    service = ValueIndexService(schema_root=tmp_path)
    service.save(ValueIndexSnapshot(
        tenant_id="tenant",
        source_fingerprint="old",
        generated_at="old",
        entries=[
            ValueIndexEntry(
                table="unchanged", column="status", value="active",
                normalized_value="active", count=2,
            ),
            ValueIndexEntry(
                table="changed", column="status", value="old",
                normalized_value="old", count=2,
            ),
            ValueIndexEntry(
                table="removed", column="status", value="gone",
                normalized_value="gone", count=2,
            ),
        ],
    ))
    current = _snapshot("new", _table("unchanged"), _table("changed", value="new"))

    index, _ = service.sync_incremental(
        current,
        changed_tables={"changed"},
        removed_tables={"removed"},
    )

    values = {(entry.table, entry.value) for entry in index.entries}
    assert ("unchanged", "active") in values
    assert ("changed", "new") in values
    assert ("changed", "old") not in values
    assert not any(table == "removed" for table, _ in values)
    assert index.source_fingerprint == "new"


@pytest.mark.asyncio
async def test_auto_update_prefers_incremental_sync_when_checkpoint_exists(monkeypatch) -> None:
    calls = {"freshness": 0, "incremental": 0}

    def freshness(**_: object) -> SemanticFreshnessResponse:
        calls["freshness"] += 1
        status = "stale" if calls["freshness"] == 1 else "up_to_date"
        return SemanticFreshnessResponse(
            status=status,
            tenant_id="tenant",
            active_catalog_exists=True,
            discovery_exists=True,
            suggestions_exist=True,
        )

    async def incremental(**_: object) -> dict[str, object]:
        calls["incremental"] += 1
        return {"status": "ready", "changes": {"changed_tables": ["employees"]}}

    monkeypatch.setattr(semantic_lifecycle_service, "check_freshness", freshness)
    monkeypatch.setattr(
        "backend.semantic.lifecycle_service.incremental_sync_service.run",
        incremental,
    )

    result = await semantic_lifecycle_service.ensure_updated("tenant")

    assert result.status == "updated"
    assert result.action == "incremental_sync"
    assert result.incremental_sync["changes"]["changed_tables"] == ["employees"]
    assert calls == {"freshness": 2, "incremental": 1}


def test_planner_reports_no_changes_for_equal_snapshots() -> None:
    previous = _snapshot("old", _table("employees"))
    current = _snapshot("new", _table("employees"))
    changes = IncrementalSyncPlanner().compare(previous, current)
    assert changes.has_changes is False
    assert changes.unchanged_tables == ("employees",)
