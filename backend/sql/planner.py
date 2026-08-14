import re
from collections import deque
from typing import List

from backend.database.models import DatabaseSchema, RelationshipInfo
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog
from backend.sql.models import SQLPlan


class SQLPlanner:
    def __init__(self):
        self.aggregation_keywords = {
            "تعداد": "COUNT",
            "مجموع": "SUM",
            "میانگین": "AVG",
            "بیشترین": "MAX",
            "بالاترین": "MAX",
            "کمترین": "MIN",
            "پایین‌ترین": "MIN",
            "پایین ترین": "MIN",
        }

    def _catalog(self, tenant_id: str | None = None, catalog: SemanticCatalog | None = None) -> SemanticCatalog:
        return catalog or load_tenant_semantic_catalog(tenant_id)

    def detect_tables(
        self,
        question: str,
        schema: DatabaseSchema,
        tenant_id: str | None = None,
        catalog: SemanticCatalog | None = None,
    ) -> List[str]:
        detected = []
        question_lower = question.lower()
        table_keywords = self._catalog(tenant_id, catalog).table_aliases()

        for table in schema.tables:
            keywords = table_keywords.get(table.name, [])
            if any(self._contains_alias(question_lower, keyword.lower()) for keyword in keywords):
                detected.append(table.name)

        if not detected:
            for table in schema.tables:
                if table.name.lower() in question_lower:
                    detected.append(table.name)

        return detected

    def _contains_alias(self, question: str, alias: str) -> bool:
        if " " in alias or "\u200c" in alias:
            return alias in question
        return re.search(rf"(?<![\wآ-ی]){re.escape(alias)}(?![\wآ-ی])", question) is not None

    def detect_joins(self, tables: List[str], relationships: List[RelationshipInfo]) -> List[dict[str, str]]:
        joins: list[dict[str, str]] = []
        seen = set()
        expanded_tables = self.expand_required_tables(tables, relationships)

        for rel in relationships:
            if rel.source_table == rel.target_table:
                continue
            if rel.source_table in expanded_tables and rel.target_table in expanded_tables:
                key = (rel.source_table, rel.source_column, rel.target_table, rel.target_column)
                if key in seen:
                    continue
                joins.append(
                    {
                        "from_table": rel.source_table,
                        "from_column": rel.source_column,
                        "to_table": rel.target_table,
                        "to_column": rel.target_column,
                    }
                )
                seen.add(key)

        return joins

    def expand_required_tables(self, tables: List[str], relationships: List[RelationshipInfo]) -> List[str]:
        ordered = list(dict.fromkeys(tables))
        if len(ordered) < 2:
            return ordered

        for target in ordered[1:]:
            path = self._shortest_relationship_path(ordered[0], target, relationships)
            for table in path:
                if table not in ordered:
                    ordered.append(table)
        return ordered

    def _shortest_relationship_path(
        self,
        start: str,
        target: str,
        relationships: List[RelationshipInfo],
    ) -> List[str]:
        if start == target:
            return [start]

        graph: dict[str, set[str]] = {}
        for rel in relationships:
            graph.setdefault(rel.source_table, set()).add(rel.target_table)
            graph.setdefault(rel.target_table, set()).add(rel.source_table)

        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            table, path = queue.popleft()
            for neighbor in sorted(graph.get(table, set())):
                if neighbor in visited:
                    continue
                next_path = [*path, neighbor]
                if neighbor == target:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return [start, target]

    def detect_aggregations(self, question: str) -> List[dict[str, str]]:
        aggregations = []

        for persian, sql in self.aggregation_keywords.items():
            if persian in question:
                aggregations.append({"function": sql, "column": "*"})

        return aggregations

    def detect_filters(self, question: str) -> List[dict[str, str]]:
        filters = []

        if "فعال" in question:
            filters.append({"column": "status", "operator": "=", "value": "'active'"})

        if "جدید" in question:
            filters.append({"column": "created_at", "operator": ">=", "value": "CURRENT_DATE - INTERVAL '30 days'"})

        return filters

    def create_plan(
        self,
        question: str,
        schema: DatabaseSchema,
        report_context: str = "",
        tenant_id: str | None = None,
        catalog: SemanticCatalog | None = None,
    ) -> SQLPlan:
        tables = self.detect_tables(question, schema, tenant_id=tenant_id, catalog=catalog)

        if not tables:
            for table in schema.tables[:3]:
                tables.append(table.name)

        tables = self.expand_required_tables(tables, schema.relationships)
        joins = self.detect_joins(tables, schema.relationships)
        aggregations = self.detect_aggregations(question)
        filters = self.detect_filters(question)

        selected_columns = ["*"]
        if aggregations:
            selected_columns = [f"{agg['function']}({agg['column']})" for agg in aggregations]

        return SQLPlan(
            required_tables=tables,
            joins=joins,
            filters=filters,
            aggregations=aggregations,
            selected_columns=selected_columns,
        )


sql_planner = SQLPlanner()
