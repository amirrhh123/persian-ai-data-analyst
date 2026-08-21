"""Ollama-assisted, schema-grounded semantic resolution."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from backend.pipeline.intent import IntentFilter, QueryIntent, normalize_persian
from backend.semantic.models import SemanticCatalog, normalize_identifier
from backend.semantic.snapshot import SemanticSnapshot
from backend.services.llm_service import llm_service
from backend.sql.structured import extract_json_object


class ResolvedFilter(BaseModel):
    column: str
    operator: str = "="
    value: str
    source: str = "semantic"


class SemanticResolution(BaseModel):
    entity: str | None = None
    requested_columns: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    filters: list[ResolvedFilter] = Field(default_factory=list)
    required_tables: list[str] = Field(default_factory=list)
    matched_semantics: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    source: str = "compiled"
    context_ids: list[str] = Field(default_factory=list)


class SemanticResolver:
    """Resolve business language before intent normalization.

    Human-approved compiled aliases are authoritative. Ollama may add only
    identifiers that exist in the same request snapshot.
    """

    ENTITY_MAP = {
        "employee": "employee", "student": "student", "school": "school",
        "organization_unit": "organization", "salary": "salary",
        "ranking_request": "ranking", "retirement_record": "retirement",
    }
    GENERIC_COLUMN_WORDS = {
        "نام", "نوع", "وضعیت", "شناسه", "شماره", "تعداد", "مقدار", "اطلاعات"
    }

    def _compiled_resolution(self, question: str, snapshot: SemanticSnapshot) -> SemanticResolution:
        normalized = normalize_identifier(normalize_persian(question))
        matched: list[str] = []
        columns: list[str] = []
        tables: list[str] = []
        entity: str | None = None
        filters: list[ResolvedFilter] = []
        metrics: list[str] = []

        for alias, table_name in snapshot.compiled.table_aliases.items():
            if alias and alias in normalized:
                table = snapshot.catalog.table(table_name)
                if table:
                    tables.append(table.name)
                    entity = entity or self.ENTITY_MAP.get(table.entity)
                    matched.append(f"{alias}->{table.name}")
        for alias, target in snapshot.compiled.column_aliases.items():
            target_table = target.split(".", 1)[0]
            if (
                alias
                and alias not in self.GENERIC_COLUMN_WORDS
                and alias in normalized
                and (not tables or target_table in tables)
            ):
                columns.append(target)
                tables.append(target.split(".", 1)[0])
                matched.append(f"{alias}->{target}")
        for alias, (column, value) in snapshot.compiled.value_aliases.items():
            if alias and alias in normalized:
                filters.append(ResolvedFilter(column=column, value=value, source="human_value_mapping"))
                tables.append(column.split(".", 1)[0])
                matched.append(f"{alias}->{column}={value}")

        for alias, metric_name in snapshot.compiled.metric_aliases.items():
            if alias and alias in normalized:
                metric = next((item for item in snapshot.catalog.metrics if item.name == metric_name), None)
                if metric:
                    metrics.append(metric.name)
                    tables.append(metric.table)
                    matched.append(f"{alias}->metric:{metric.name}")

        if entity is None:
            for table_name in tables:
                table = snapshot.catalog.table(table_name)
                if table and self.ENTITY_MAP.get(table.entity):
                    entity = self.ENTITY_MAP[table.entity]
                    break

        return SemanticResolution(
            entity=entity,
            requested_columns=list(dict.fromkeys(columns)),
            filters=filters,
            metrics=list(dict.fromkeys(metrics)),
            required_tables=list(dict.fromkeys(tables)),
            matched_semantics=matched,
            confidence=1.0 if matched else 0.0,
            source="compiled",
        )

    def _context(self, catalog: SemanticCatalog) -> str:
        lines: list[str] = []
        for table in catalog.tables:
            lines.append(f"TABLE {table.name}; entity={table.entity}; aliases={table.aliases}")
            for column in table.columns:
                lines.append(f"COLUMN {table.name}.{column.name}; aliases={column.aliases}; type={column.value_type or column.data_type}")
        for rule in catalog.rules:
            lines.append(f"RULE {rule.description}; applies_to={rule.applies_to}")
        for mapping in catalog.value_mappings:
            lines.append(f"VALUE {mapping}")
        for metric in catalog.metrics:
            lines.append(f"METRIC {metric.name}; table={metric.table}; expression={metric.expression}; aliases={metric.aliases}")
        for join in catalog.joins:
            lines.append(f"JOIN {join.from_table}.{join.from_column}->{join.to_table}.{join.to_column}")
        return "\n".join(lines)

    async def resolve(self, question: str, snapshot: SemanticSnapshot) -> SemanticResolution:
        compiled = self._compiled_resolution(question, snapshot)
        context_matches = snapshot.context_index.search(
            question,
            allowed_tables=set(compiled.required_tables) or None,
        )
        compiled.context_ids = [match.document.id for match in context_matches]
        # Approved compiled semantics are deterministic and authoritative.
        # Ollama still receives the same snapshot during SQL generation/review;
        # a second model call is reserved for unresolved or ambiguous language.
        if compiled.confidence == 1.0 and compiled.entity and compiled.matched_semantics:
            return compiled
        indexed_context = "\n".join(match.document.text for match in context_matches)
        if not indexed_context:
            indexed_context = self._context(snapshot.catalog)
        prompt = f"""Resolve this Persian database question using ONLY the semantic catalog below.
Return strict JSON: {{"entity":null,"requested_columns":[],"metrics":[],"filters":[],"required_tables":[],"matched_semantics":[],"confidence":0.0,"source":"ollama"}}.
Every requested column and filter column must be a fully qualified table.column from the catalog. Never invent a value or add an implicit status.

Question: {question}

Relevant semantic context from catalog version {snapshot.version}:
{indexed_context}"""
        try:
            raw = await llm_service.chat(
                prompt,
                "You are a semantic resolver, not a SQL generator. Return only valid JSON grounded in the supplied catalog.",
            )
            llm_result = SemanticResolution.model_validate(json.loads(extract_json_object(raw)))
        except Exception:  # Provider failures must fall back to compiled human rules.
            return compiled
        return self._merge_grounded(compiled, llm_result, snapshot.catalog, question)

    def _merge_grounded(
        self,
        compiled: SemanticResolution,
        llm_result: SemanticResolution,
        catalog: SemanticCatalog,
        question: str,
    ) -> SemanticResolution:
        valid_tables = {table.name for table in catalog.tables}
        valid_columns = {
            f"{table.name}.{column.name}"
            for table in catalog.tables
            for column in table.columns
        }
        columns = [*compiled.requested_columns]
        normalized_question = normalize_identifier(question)

        def column_is_mentioned(target: str) -> bool:
            table_name, column_name = target.split(".", 1)
            table = catalog.table(table_name)
            column = table.column(column_name) if table else None
            return bool(column and any(
                normalize_identifier(alias) in normalized_question
                for alias in [column.name, *column.aliases]
                if alias
            ))

        columns.extend(
            item for item in llm_result.requested_columns
            if item in valid_columns and column_is_mentioned(item)
        )
        filters = [*compiled.filters]
        compiled_filter_keys = {(item.column, item.value) for item in compiled.filters}
        filters.extend(
            item for item in llm_result.filters
            if item.column in valid_columns
            and (
                normalize_identifier(item.value) in normalized_question
                or (item.column, item.value) in compiled_filter_keys
            )
        )
        tables = [*compiled.required_tables]
        tables.extend(item for item in llm_result.required_tables if item in valid_tables)
        valid_entities = set(self.ENTITY_MAP.values())
        grounded_entity = llm_result.entity if llm_result.entity in valid_entities else None
        return SemanticResolution(
            entity=compiled.entity or grounded_entity,
            requested_columns=list(dict.fromkeys(columns)),
            metrics=list(dict.fromkeys([*compiled.metrics, *[m for m in llm_result.metrics if m in {x.name for x in catalog.metrics}]])),
            filters=filters,
            required_tables=list(dict.fromkeys(tables)),
            matched_semantics=list(dict.fromkeys([*compiled.matched_semantics, *llm_result.matched_semantics])),
            confidence=max(compiled.confidence, llm_result.confidence),
            source="compiled+ollama",
            context_ids=list(dict.fromkeys([*compiled.context_ids, *llm_result.context_ids])),
        )

    def enrich_intent(self, intent: QueryIntent, resolution: SemanticResolution) -> QueryIntent:
        if not intent.requested_entity and resolution.entity:
            intent.requested_entity = resolution.entity
        for qualified in resolution.requested_columns:
            column = qualified.split(".", 1)[-1]
            filter_value = getattr(intent, column, None) if hasattr(intent, column) else None
            if filter_value not in (None, "") and column not in intent.grouping:
                # A phrase such as "استان تهران" is a filter, not a requested
                # output column unless the user explicitly asks for grouping.
                continue
            if column not in intent.requested_columns:
                intent.requested_columns.append(column)
        for metric in resolution.metrics:
            if metric not in intent.semantic_metrics:
                intent.semantic_metrics.append(metric)
        existing = {(item.column, item.operator, item.value) for item in intent.filters}
        for item in resolution.filters:
            column = item.column.split(".", 1)[-1]
            key = (column, item.operator, item.value)
            if key not in existing:
                intent.filters.append(IntentFilter(column=column, operator=item.operator, value=item.value))
            if hasattr(intent, column) and getattr(intent, column) in (None, ""):
                setattr(intent, column, item.value)
        return intent


semantic_resolver = SemanticResolver()
