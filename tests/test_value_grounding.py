"""Offline tests for database value grounding (roadmap Change 3)."""

from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.value_index.extractor import (
    CandidateValue,
    extract_candidate_values,
    extract_numeric_phrases,
)
from backend.value_index.models import ValueIndexMatch, ValueIndexSnapshot
from backend.value_index.ranker import rank_matches
from backend.value_index.resolver import GroundingResult, value_grounding_resolver
from backend.value_index.service import value_index_service


# ----------------------------------------------------------------------
# Extractor
# ----------------------------------------------------------------------

def test_extractor_finds_quoted_spans():
    values = extract_candidate_values("تعداد موارد با «کارمند اداری» را بگو")
    assert any(item.text == "کارمند اداری" for item in values)


def test_numeric_phrase_with_unit_and_comparison():
    phrases = extract_numeric_phrases("هزینه کمتر از ۸۰ میلیون")
    assert len(phrases) == 1
    assert phrases[0].amount == 80_000_000
    assert phrases[0].comparison_hint == "<"


def test_numeric_phrase_billion():
    phrases = extract_numeric_phrases("بیشتر از 1.5 میلیارد")
    assert phrases[0].amount == 1_500_000_000
    assert phrases[0].comparison_hint == ">"


# ----------------------------------------------------------------------
# Ranker
# ----------------------------------------------------------------------

def _match(table, column, value, score=0.7, label=False):
    return ValueIndexMatch(
        table=table,
        column=column,
        value=value,
        count=5,
        score=score,
        label_matched=label,
        matched_label="پست" if label else None,
    )


def test_entity_relevant_match_gets_boost():
    outcome = rank_matches(
        [_match("employees", "position", "مدیر"), _match("demo_training_requests", "requester_role", "مدیر")],
        requested_entity="employee",
    )
    assert outcome.ranked[0].match.table == "employees"
    assert outcome.ranked[0].entity_relevant is True


def test_close_scores_across_tables_flag_ambiguity():
    strong = _match("a_table", "col", "تهران", score=0.90)
    close = _match("b_table", "col", "تهران", score=0.88)
    far = _match("c_table", "other", "شیراز", score=0.40)
    outcome = rank_matches([strong, close, far])
    assert outcome.is_ambiguous
    assert {"a_table", "b_table"} == set(outcome.ambiguous_tables)


# ----------------------------------------------------------------------
# Resolver (injected search fn - no disk access)
# ----------------------------------------------------------------------

def _fake_search_factory(matches):
    def search_fn(text):
        return [m for m in matches if m.value in text]
    return search_fn


def _empty_index() -> ValueIndexSnapshot:
    return ValueIndexSnapshot(tenant_id="t", source_fingerprint="f", generated_at="now", entries=[])


def test_resolver_grounds_value_to_column():
    matches = [
        _match("demo_training_requests", "requester_role", "کارمند اداری", score=0.85),
        _match("employees", "position", "کارشناس", score=0.60),
    ]
    result = value_grounding_resolver.resolve(
        "تعداد موارد با کارمند اداری",
        index=_empty_index(),
        search_fn=_fake_search_factory(matches),
    )
    assert result.recommended_table == "demo_training_requests"
    assert result.grounded_filters[0].column == "requester_role"
    assert result.found_any


def test_resolver_reports_ambiguity_without_recommendation():
    matches = [
        _match("table_a", "col", "تهران", score=0.90),
        _match("table_b", "col", "تهران", score=0.88),
    ]
    result = value_grounding_resolver.resolve(
        "آمار تهران",
        index=None,
        search_fn=_fake_search_factory(matches),
    )
    assert result.recommended_table is None
    assert set(result.ambiguous_tables) == {"table_a", "table_b"}
    assert len(result.grounded_filters) >= 2


def test_resolver_full_question_search_when_no_quoted_candidates():
    matches = [_match("demo_training_requests", "status", "active", score=0.8)]
    result = value_grounding_resolver.resolve(
        "تعداد درخواست های active",
        index=None,
        search_fn=_fake_search_factory(matches),
    )
    assert result.recommended_table == "demo_training_requests"


def test_audit_payload_contains_only_safe_evidence():
    payload = GroundingResult().audit_payload()
    assert "grounded_filters" in payload and "candidates" in payload


# ----------------------------------------------------------------------
# Security: index building excludes sensitive/identifier columns
# ----------------------------------------------------------------------

def _snapshot_with(columns):
    table = DiscoveredTableInfo(
        name="t1",
        row_count=100,
        columns=[
            DiscoveredColumnInfo(
                name=name,
                data_type=data_type,
                udt_name="varchar",
                is_primary_key=pk,
                sample_values=[
                    ColumnSampleValue(value=value, count=count)
                    for value, count in samples
                ],
            )
            for name, data_type, pk, samples in columns
        ],
    )
    return SchemaDiscoverySnapshot(
        tenant_id="sec",
        database_name="db",
        fingerprint="fp",
        generated_at="now",
        tables=[table],
    )


def test_sensitive_columns_never_indexed():
    snapshot = _snapshot_with(
        [
            ("national_id", "character varying", False, [("8223876400", 10)]),
            ("password_hash", "text", False, [("secret", 10)]),
            ("status", "character varying", False, [("active", 10)]),
            ("id", "integer", True, [("1", 10)]),
        ]
    )
    index = value_index_service.build(snapshot)
    indexed_columns = {entry.column for entry in index.entries}
    assert "status" in indexed_columns
    assert "national_id" not in indexed_columns
    assert "password_hash" not in indexed_columns
    assert "id" not in indexed_columns
    assert index.excluded_columns["t1.national_id"] == "sensitive_column"


def test_high_cardinality_text_columns_excluded():
    snapshot = _snapshot_with(
        [("note", "text", False, [("x1", 1), ("x2", 1), ("x3", 1)])]
    )
    index = value_index_service.build(snapshot)
    assert index.excluded_columns.get("t1.note") == "high_cardinality_samples"
