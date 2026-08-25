"""Offline tests for name-based join inference (accuracy work #4)."""

from backend.database.join_inference import (
    augment_relationships,
    infer_relationships,
    singularize,
)
from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    RelationshipInfo,
)


def _table(name, columns, pk="id"):
    return DiscoveredTableInfo(
        schema_name="public",
        name=name,
        comment=None,
        row_count=100,
        columns=[
            DiscoveredColumnInfo(
                name=col_name,
                data_type=data_type,
                udt_name="int4" if data_type == "integer" else "varchar",
                is_primary_key=(col_name == pk),
                sample_values=[ColumnSampleValue(value="x", count=1)],
            )
            for col_name, data_type in columns
        ],
        primary_keys=[pk] if pk else [],
    )


def _fk(source_table, source_column, target_table):
    return RelationshipInfo(
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column="id",
        relationship_type="many_to_one",
    )


def _tables():
    return [
        _table("customers", [("id", "integer"), ("name", "character varying")]),
        _table("customer", [("id", "integer")]),
        _table("orders", [("id", "integer"), ("customer_id", "integer"), ("total", "numeric")]),
        # No id column -> must never become a join target.
        _table("logs", [("id", "integer"), ("order_id", "text")]),
        _table("statuses", [("id", "integer"), ("name", "character varying")]),
        _table("events", [("id", "integer"), ("status_id", "bigint")]),
    ]


def test_singularize_handles_common_plurals():
    assert singularize("organizations") == "organization"
    assert singularize("employees") == "employee"
    assert singularize("companies") == "company"
    assert singularize("statuses") == "status"
    assert singularize("classes") == "class"
    assert singularize("customer") == "customer"


def test_basic_fk_less_join_is_inferred():
    tables = [_t() for _t in ()] or [
        _table("customers", [("id", "integer")]),
        _table("orders", [("id", "integer"), ("customer_id", "integer")]),
    ]
    inferred = infer_relationships(tables, existing_relationships=[])
    pairs = {(r.source_table, r.source_column, r.target_table) for r in inferred}
    assert ("orders", "customer_id", "customers") in pairs
    rel = next(r for r in inferred if r.source_column == "customer_id")
    assert rel.relationship_type == "inferred_name_match"
    assert rel.target_column == "id"


def test_plural_and_singular_targets_both_match():
    tables = [
        _table("organization_unit", [("id", "integer")]),
        _table("organization_units", [("id", "integer")]),
        _table("employees", [("id", "integer"), ("organization_unit_id", "integer")]),
    ]
    inferred = infer_relationships(tables, existing_relationships=[])
    targets = {r.target_table for r in inferred if r.source_column == "organization_unit_id"}
    assert targets == {"organization_unit", "organization_units"}


def test_real_foreign_keys_are_not_duplicated():
    tables = [
        _table("customers", [("id", "integer")]),
        _table("orders", [("id", "integer"), ("customer_id", "integer")]),
    ]
    existing = [_fk("orders", "customer_id", "customers")]
    all_rels, added = augment_relationships(tables, existing)
    customer_joins = [r for r in all_rels if r.source_column == "customer_id"]
    assert len(customer_joins) == 1
    assert customer_joins[0].relationship_type == "many_to_one"
    assert added == 0


def test_pk_columns_never_become_sources():
    tables = [
        _table("customers", [("id", "integer")]),
    ]
    assert infer_relationships(tables, existing_relationships=[]) == []


def test_tables_without_id_are_not_join_targets():
    tables = [
        _table("audit_log", [("entry_id", "integer")]),  # no literal 'id' column
        _table("events", [("id", "integer"), ("audit_id", "integer")]),
    ]
    assert infer_relationships(tables, existing_relationships=[]) == []


def test_text_to_integer_type_mismatch_is_skipped():
    tables = [
        _table("customers", [("id", "integer")]),
        _table("refs", [("id", "integer")]),
        _table("notes", [("id", "integer"), ("customer_ref_id", "text")]),
    ]
    inferred = infer_relationships(tables, existing_relationships=[])
    # customer_ref_id is text; customers.id integer -> no match.
    assert all(r.target_table != "customers" for r in inferred)


def test_self_referencing_join_excluded():
    tables = [
        _table("employees", [("id", "integer"), ("manager_id", "integer")]),
    ]
    assert infer_relationships(tables, existing_relationships=[]) == []


def test_augment_reports_added_count():
    tables = [
        _table("customers", [("id", "integer")]),
        _table("orders", [("id", "integer"), ("customer_id", "integer")]),
    ]
    _all, added = augment_relationships(tables, [])
    assert added >= 1
