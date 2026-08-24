"""Offline tests for deep value indexing + fuzzy grounding (accuracy work #1)."""

from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.value_index.models import ValueIndexEntry, ValueIndexSnapshot
from backend.value_index.service import ValueIndexService


def _service() -> ValueIndexService:
    return ValueIndexService()


# ----------------------------------------------------------------------
# Fuzzy search tiers
# ----------------------------------------------------------------------

def _index(*values, table="t", column="c"):
    entries = []
    for value in values:
        normalized = ValueIndexService.normalize(value)
        entries.append(
            ValueIndexEntry(
                table=table,
                column=column,
                value=value,
                normalized_value=normalized,
                count=5,
                column_aliases=[],
            )
        )
    return ValueIndexSnapshot(
        tenant_id="t", source_fingerprint="f", generated_at="now", entries=entries
    )


def test_exact_match_still_highest_and_marked_exact():
    service = _service()
    index = _index("کارمند اداری")
    matches = service.search("تعداد موارد با کارمند اداری", index=index)
    assert matches
    assert matches[0].match_kind == "exact"


def test_plural_tolerance_matches_via_fuzzy_or_token():
    service = _service()
    index = _index("کارمند اداری")
    matches = service.search("تعداد کارمندان اداری", index=index)
    assert matches, "plural «کارمندان» should still ground to «کارمند اداری»"
    assert matches[0].match_kind in {"token", "fuzzy"}


def test_token_subset_matches_reordered_words():
    service = _service()
    index = _index("دوره امور مالی")
    matches = service.search("امور مالی دوره چند تا است", index=index)
    assert matches
    assert matches[0].match_kind == "token"
    exact = service.search("تعداد دوره امور مالی", index=_index("دوره امور مالی"))
    assert exact[0].match_kind == "exact"


def test_single_typo_within_distance_matches_fuzzy():
    service = _service()
    index = _index("مدیر مدرسه")
    matches = service.search("تعداد مدیر مدسه", index=index)  # «مدرسه» missing ر
    assert any(m.match_kind == "fuzzy" for m in matches)


def test_unrelated_question_does_not_fuzzy_match():
    service = _service()
    index = _index("کارمند اداری")
    matches = service.search("تعداد دانش آموزان", index=index)
    assert matches == []


def test_fuzzy_scores_below_exact_equivalent():
    service = _service()
    index = _index("کارمند اداری")
    fuzzy = service.search("تعداد کارمندان اداری", index=index)
    exact = service.search("تعداد کارمند اداری", index=index)
    assert fuzzy[0].score <= exact[0].score


def test_disabled_fuzzy_restores_exact_only():
    service = _service()
    service.settings.value_index_fuzzy_enabled = False
    index = _index("کارمند اداری")
    matches = service.search("تعداد کارمندان اداری", index=index)
    assert matches == []


def test_sensitive_column_never_searchable_even_if_indexed_manually():
    """Defense-in-depth: search filters by caller-provided columns too."""
    service = _service()
    index = _index("8223876400", table="employees", column="national_id")
    matches = service.search("کد ملی ۸۲۲۳۸۷۶۴۰۰", index=index, columns={"position"})
    assert matches == []


# ----------------------------------------------------------------------
# Deep refresh
# ----------------------------------------------------------------------

def _discovery(columns):
    table = DiscoveredTableInfo(
        name="requests",
        row_count=5000,
        columns=[
            DiscoveredColumnInfo(
                name=name,
                data_type=data_type,
                udt_name="varchar",
                is_primary_key=pk,
                sample_values=[ColumnSampleValue(value=v, count=c) for v, c in samples],
            )
            for name, data_type, pk, samples in columns
        ],
    )
    return SchemaDiscoverySnapshot(
        tenant_id="deep",
        database_name="db",
        fingerprint="fp",
        generated_at="now",
        tables=[table],
    )


def _base_index(discovery):
    service = _service()
    return service.build(discovery)


def test_deep_refresh_replaces_samples_with_full_distinct():
    service = _service()
    discovery = _discovery(
        [
            ("status", "character varying", False, [("act", 1)]),
            ("id", "integer", True, [("1", 5)]),
        ]
    )
    sampled = _base_index(discovery)

    def executor(sql):
        assert "GROUP BY" in sql and "LIMIT" in sql
        return [("active", 300), ("pending", 150), ("rejected", 50)]

    merged, stats = service.deep_refresh(sampled, discovery, executor=executor)

    status_values = {e.value: e.count for e in merged.entries if e.column == "status"}
    assert status_values == {"active": 300, "pending": 150, "rejected": 50}
    assert stats["indexed"] >= 1
    assert all(e.column != "id" for e in merged.entries)


def test_high_cardinality_columns_are_skipped_and_flagged():
    service = _service()
    service.settings.value_index_max_distinct = 2
    discovery = _discovery([("note", "text", False, [("x", 1)])])
    sampled = _base_index(discovery)

    def executor(sql):
        return [(f"v{i}", 1) for i in range(10)]  # more than cap of 2

    merged, stats = service.deep_refresh(sampled, discovery, executor=executor)
    assert stats["skipped_cardinality"] >= 1
    assert merged.excluded_columns.get("requests.note") == "deep_high_cardinality"
    # Nothing was indexed for the high-cardinality column...
    assert all(e.column != "note" for e in merged.entries)


def test_deep_refresh_respects_security_exclusions():
    service = _service()
    discovery = _discovery(
        [
            ("national_id", "character varying", False, [("123", 2)]),
            ("status", "character varying", False, [("active", 2)]),
        ]
    )
    sampled = _base_index(discovery)

    executed = []

    def executor(sql):
        executed.append(sql)
        return [("active", 9)]

    merged, _stats = service.deep_refresh(sampled, discovery, executor=executor)
    assert len(executed) == 1  # national_id is never queried
    assert all(e.column != "national_id" for e in merged.entries)
    reason = merged.excluded_columns.get("requests.national_id")
    assert reason in {"sensitive_column", None} and reason != "deep_high_cardinality"


def test_executor_errors_keep_sampled_entries():
    service = _service()
    discovery = _discovery([("status", "character varying", False, [("sampled", 5)])])
    sampled = _base_index(discovery)

    def broken_executor(sql):
        raise RuntimeError("db down")

    merged, stats = service.deep_refresh(sampled, discovery, executor=broken_executor)
    assert stats["errors"] >= 1
    assert any(e.value == "sampled" for e in merged.entries)


def test_budget_limits_number_of_scanned_columns():
    service = _service()
    service.settings.value_index_deep_column_budget = 1
    discovery = _discovery(
        [
            ("alpha", "character varying", False, [("a", 1)]),
            ("beta", "character varying", False, [("b", 1)]),
        ]
    )
    sampled = _base_index(discovery)
    scanned = []

    def executor(sql):
        scanned.append(sql)
        return [("v", 3)]

    service.deep_refresh(sampled, discovery, executor=executor)
    assert len(scanned) == 1
