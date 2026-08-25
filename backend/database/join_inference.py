"""Conservative name-based join inference for FK-less client schemas.

Many real-world databases lack foreign keys. Without them the join verifier
correctly refuses multi-table questions, so such schemas degrade to
clarification loops. This module recovers the obvious cases deterministically:

    customers.id  <-  orders.customer_id
    organization_units.id  <-  employees.organization_unit_id

Only ``*_id`` columns pointing at a table whose primary key is literally
``id`` are considered, with simple English plural handling and a type-sanity
check. Inferred relationships are tagged ``inferred_name_match`` so they stay
auditable and distinguishable from declared FKs everywhere downstream.
"""

from __future__ import annotations

from typing import Iterable, List, Set

from backend.database.models import (
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    RelationshipInfo,
)

_RELATIONSHIP_TYPE = "inferred_name_match"
_INTEGER_TYPES = {"integer", "bigint", "smallint", "serial", "bigserial"}
_TEXT_TYPES = {"character varying", "character", "text", "USER-DEFINED"}


def singularize(table_name: str) -> str:
    """Very small English de-pluralizer tuned for schema naming."""
    name = table_name.lower()
    if len(name) > 4 and name.endswith("ies"):
        return name[:-3] + "y"           # companies -> company
    if len(name) > 3 and name.endswith("ses"):
        return name[:-2]                 # statuses -> status, classes -> class
    if len(name) > 3 and name.endswith("es") and name[-3] in "sxz":
        return name[:-2]                 # boxes -> box
    if len(name) > 2 and name.endswith("s"):
        return name[:-1]                 # organizations -> organization
    return name


def _plural_candidates(table_name: str) -> Iterable[str]:
    yield table_name
    yield table_name + "s"
    yield table_name + "es"


def _names_for_lookup(tables: List[DiscoveredTableInfo]) -> dict[str, DiscoveredTableInfo]:
    return {table.name.lower(): table for table in tables}


def _type_compatible(source: DiscoveredColumnInfo, target: DiscoveredColumnInfo) -> bool:
    source_type = (source.data_type or "").lower()
    target_type = (target.data_type or "").lower()
    if source_type in _INTEGER_TYPES and target_type in _INTEGER_TYPES:
        return True
    if source_type in _TEXT_TYPES and target_type in _TEXT_TYPES:
        return True
    return False


def _target_id_column(table: DiscoveredTableInfo) -> DiscoveredColumnInfo | None:
    for column in table.columns:
        if column.name.lower() == "id":
            return column
    return None


def infer_relationships(
    tables: List[DiscoveredTableInfo],
    *,
    existing_relationships: List[RelationshipInfo],
) -> List[RelationshipInfo]:
    """Return inferred many_to_one relationships not already covered."""
    known: Set[tuple[str, str, str, str]] = {
        (
            rel.source_table.lower(),
            rel.source_column.lower(),
            rel.target_table.lower(),
            rel.target_column.lower(),
        )
        for rel in existing_relationships
    }
    lookup = _names_for_lookup(tables)
    inferred: List[RelationshipInfo] = []

    for table in tables:
        for column in table.columns:
            name_lower = column.name.lower()
            if not name_lower.endswith("_id"):
                continue
            if column.name in (table.primary_keys or []) or column.is_primary_key:
                continue
            base = singularize(name_lower[: -len("_id")])

            # Match either direction: table may be singular (== base) or a
            # plural form of it; existing table names also de-pluralized so
            # e.g. column person_id hits a table literally named people's
            # singular sibling.
            candidate_tables = {base}
            candidate_tables.update(_plural_candidates(base))
            candidate_tables.update(singularize(candidate) for candidate in lookup)
            matches = [
                lookup[candidate]
                for candidate in sorted(set(candidate_tables) & set(lookup.keys()))
                if candidate != table.name.lower()
            ]

            for target in matches:
                target_id = _target_id_column(target)
                if target_id is None:
                    continue
                if not _type_compatible(column, target_id):
                    continue
                key = (
                    table.name.lower(),
                    column.name.lower(),
                    target.name.lower(),
                    "id",
                )
                if key in known:
                    continue
                known.add(key)
                inferred.append(
                    RelationshipInfo(
                        source_table=table.name,
                        source_column=column.name,
                        target_table=target.name,
                        target_column="id",
                        relationship_type=_RELATIONSHIP_TYPE,
                    )
                )

    return inferred


def augment_relationships(
    tables: List[DiscoveredTableInfo],
    relationships: List[RelationshipInfo],
) -> tuple[List[RelationshipInfo], int]:
    """Append inferred joins to real FK relationships; returns (all, added_count)."""
    inferred = infer_relationships(tables, existing_relationships=relationships)
    return [*relationships, *inferred], len(inferred)
