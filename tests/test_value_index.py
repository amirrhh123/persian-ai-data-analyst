"""Behavior tests for the generic database value index."""

from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.pipeline.query_pipeline import QueryPipeline
from backend.semantic.models import SemanticColumn, SemanticTable
from backend.value_index.models import ValueIndexMatch
from backend.value_index.service import ValueIndexService


def _column(
    name: str,
    values: list[tuple[str, int]],
    *,
    primary: bool = False,
    unique: bool = False,
) -> DiscoveredColumnInfo:
    return DiscoveredColumnInfo(
        name=name,
        data_type="text",
        udt_name="text",
        is_primary_key=primary,
        is_unique=unique,
        sample_values=[
            ColumnSampleValue(value=value, count=count) for value, count in values
        ],
    )


def _snapshot() -> SchemaDiscoverySnapshot:
    return SchemaDiscoverySnapshot(
        tenant_id="tenant",
        database_name="test_db",
        generated_at="2026-08-14T12:00:00",
        fingerprint="schema-v1",
        tables=[
            DiscoveredTableInfo(
                name="requests",
                row_count=100,
                columns=[
                    _column("id", [("1", 1)], primary=True),
                    _column("national_id", [("1234567890", 1)], unique=True),
                    _column("requester_role", [("کارمند اداری", 32), ("مدیر", 8)]),
                    _column("status", [("فعال", 55), ("بسته", 45)]),
                    _column("tracking_code", [("A-1", 1), ("A-2", 1)]),
                ],
            )
        ],
    )


def test_build_indexes_categorical_values_and_excludes_sensitive_columns() -> None:
    service = ValueIndexService()

    index = service.build(_snapshot())

    indexed_columns = {entry.column for entry in index.entries}
    assert "requester_role" in indexed_columns
    assert "status" in indexed_columns
    assert "id" not in indexed_columns
    assert "national_id" not in indexed_columns
    assert "tracking_code" not in indexed_columns


def test_search_normalizes_persian_arabic_characters() -> None:
    service = ValueIndexService()
    index = service.build(_snapshot())

    matches = service.search("درخواست با پست كارمند اداري", index=index)

    assert matches[0].table == "requests"
    assert matches[0].column == "requester_role"
    assert matches[0].value == "کارمند اداری"
    assert matches[0].score > 0.5


def test_search_marks_column_label_evidence() -> None:
    service = ValueIndexService()
    index = service.build(
        _snapshot(),
        column_aliases={"requests.requester_role": ["پست", "سمت"]},
    )

    matches = service.search("تعداد درخواست‌ها با پست کارمند اداری", index=index)

    assert matches[0].label_matched is True
    assert matches[0].matched_label == "پست"


def test_save_and_load_preserve_source_fingerprint(tmp_path) -> None:
    service = ValueIndexService(schema_root=tmp_path)
    index = service.build(_snapshot())

    output_path = service.save(index)
    loaded = service.load("tenant")

    assert output_path == tmp_path / "tenants" / "tenant" / "value_index.json"
    assert loaded is not None
    assert loaded.source_fingerprint == "schema-v1"
    assert len(loaded.entries) == len(index.entries)


def test_search_returns_empty_for_missing_or_partial_value() -> None:
    service = ValueIndexService()
    index = service.build(_snapshot())

    assert service.search("کارمند", index=index) == []
    assert service.search("مقدار ناشناخته", index=index) == []


def test_query_pipeline_uses_value_index_when_discovery_sample_is_empty(
    monkeypatch,
) -> None:
    pipeline = QueryPipeline()
    table = SemanticTable(
        name="requests",
        entity="request",
        description="درخواست‌ها",
        columns=[
            SemanticColumn(
                name="requester_role",
                data_type="text",
                description="پست درخواست‌دهنده",
                aliases=["پست", "سمت"],
            )
        ],
    )
    discovery = SchemaDiscoverySnapshot(
        tenant_id="tenant",
        database_name="test_db",
        generated_at="2026-08-14T12:00:00",
        fingerprint="schema-v1",
        tables=[DiscoveredTableInfo(name="requests", columns=[])],
    )
    monkeypatch.setattr(
        "backend.pipeline.query_pipeline.value_index_service.search",
        lambda *args, **kwargs: [
            ValueIndexMatch(
                table="requests",
                column="requester_role",
                value="کارمند اداری",
                count=32,
                score=0.95,
                label_matched=True,
                matched_label="پست",
            )
        ],
    )

    matches = pipeline._sample_value_mentions_for_table(
        "درخواست‌ها با پست کارمند اداری",
        table,
        discovery,
    )

    assert matches == [("requester_role", "کارمند اداری", 12, 32)]
