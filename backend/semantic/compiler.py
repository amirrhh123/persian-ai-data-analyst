"""Compile human-reviewed semantic metadata into deterministic lookup rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.semantic.models import SemanticCatalog, normalize_identifier


@dataclass(frozen=True, slots=True)
class CompiledSemanticRules:
    """Fast, executable representation of one semantic catalog version."""

    table_aliases: dict[str, str] = field(default_factory=dict)
    column_aliases: dict[str, str] = field(default_factory=dict)
    value_aliases: dict[str, tuple[str, str]] = field(default_factory=dict)
    metric_aliases: dict[str, str] = field(default_factory=dict)
    join_paths: tuple[tuple[str, str, str, str], ...] = ()

    def resolve_table(self, phrase: str) -> str | None:
        return self.table_aliases.get(normalize_identifier(phrase))

    def resolve_column(self, phrase: str) -> str | None:
        return self.column_aliases.get(normalize_identifier(phrase))


class SemanticCompiler:
    """Compile catalog entries with deterministic human-first precedence."""

    def compile(self, catalog: SemanticCatalog) -> CompiledSemanticRules:
        tables: dict[str, str] = {}
        columns: dict[str, str] = {}
        values: dict[str, tuple[str, str]] = {}
        metrics: dict[str, str] = {}

        for table in catalog.tables:
            for alias in [table.name, *table.aliases]:
                tables[normalize_identifier(alias)] = table.name
            for column in table.columns:
                target = f"{table.name}.{column.name}"
                for alias in [column.name, *column.aliases]:
                    columns[normalize_identifier(alias)] = target

        for mapping in catalog.value_mappings:
            column = str(mapping.get("column", ""))
            value = str(mapping.get("value", ""))
            for alias in [mapping.get("term_fa", ""), *mapping.get("aliases_fa", [])]:
                if alias:
                    values[normalize_identifier(str(alias))] = (column, value)

        # Approved business terms override inferred column aliases.
        for term in catalog.business_terms:
            target = str(term.get("maps_to", ""))
            for alias in [term.get("term_fa", ""), *term.get("aliases_fa", [])]:
                if alias and target:
                    columns[normalize_identifier(str(alias))] = target

        for metric in catalog.metrics:
            for alias in [metric.name, *metric.aliases]:
                metrics[normalize_identifier(alias)] = metric.name

        joins = tuple(
            (join.from_table, join.from_column, join.to_table, join.to_column)
            for join in catalog.joins
        )
        return CompiledSemanticRules(tables, columns, values, metrics, joins)


semantic_compiler = SemanticCompiler()
