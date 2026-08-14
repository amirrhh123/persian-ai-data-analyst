from __future__ import annotations

from collections import deque

from backend.database.models import RelationshipInfo
from backend.pipeline.intent import NormalizedIntent
from backend.semantic.models import SemanticCatalog
from backend.sql.models import JoinVerificationResult, SQLPlan


REQUIRED_TABLES_BY_ENTITY_FILTER = {
    ("student", "province"): ["students", "schools", "organization_units"],
    ("student", "city"): ["students", "schools", "organization_units"],
    ("student", "school_name"): ["students", "schools"],
    ("school", "province"): ["schools", "organization_units"],
    ("school", "city"): ["schools", "organization_units"],
    ("employee", "province"): ["employees", "organization_units"],
    ("employee", "city"): ["employees", "organization_units"],
    ("salary", "province"): ["salary_items", "employees", "organization_units"],
    ("salary", "city"): ["salary_items", "employees", "organization_units"],
    ("retirement", "national_id"): ["retirement_records", "employees"],
}


class SQLPlanJoinVerifier:
    def verify(
        self,
        plan: SQLPlan,
        catalog: SemanticCatalog,
        normalized: NormalizedIntent | None = None,
    ) -> JoinVerificationResult:
        errors: list[str] = []
        warnings: list[str] = []
        missing_tables: list[str] = []
        disconnected_tables: list[str] = []
        suggested_joins: list[dict[str, str]] = []

        required_tables = list(dict.fromkeys(plan.required_tables))
        catalog_tables = {table.name for table in catalog.tables}
        unknown_tables = [table for table in required_tables if table not in catalog_tables]
        if unknown_tables:
            errors.append(f"Unknown tables in SQL plan: {', '.join(unknown_tables)}")

        expected_tables = self._expected_tables(normalized)
        for table in expected_tables:
            if table not in required_tables:
                missing_tables.append(table)
        if missing_tables:
            errors.append(f"SQL plan is missing required join-path tables: {', '.join(missing_tables)}")

        relationships = self._relationships(catalog)
        if len(required_tables) > 1:
            disconnected_tables = self._disconnected_tables(required_tables, plan.joins)
            if disconnected_tables:
                errors.append(f"SQL plan join graph is disconnected: {', '.join(disconnected_tables)}")

            needed = self._needed_path_joins(required_tables, relationships)
            for join in needed:
                if not self._has_join(plan.joins, join):
                    suggested_joins.append(join)
            if suggested_joins:
                errors.append("SQL plan is missing one or more required joins.")

        duplicate_count = len(plan.joins) - len({self._join_key(join) for join in plan.joins})
        if duplicate_count:
            warnings.append(f"SQL plan has {duplicate_count} duplicate join(s).")

        self_joins = [join for join in plan.joins if join.get("from_table") == join.get("to_table")]
        if self_joins:
            errors.append("SQL plan contains self-joins without an explicit alias strategy.")

        return JoinVerificationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            missing_tables=missing_tables,
            disconnected_tables=disconnected_tables,
            suggested_joins=suggested_joins,
        )

    def _expected_tables(self, normalized: NormalizedIntent | None) -> list[str]:
        if not normalized or not normalized.entity:
            return []
        expected: list[str] = []
        for item in normalized.filters:
            for table in REQUIRED_TABLES_BY_ENTITY_FILTER.get((normalized.entity, item.field), []):
                if table not in expected:
                    expected.append(table)
        return expected

    def _relationships(self, catalog: SemanticCatalog) -> list[RelationshipInfo]:
        return [
            RelationshipInfo(
                source_table=join.from_table,
                source_column=join.from_column,
                target_table=join.to_table,
                target_column=join.to_column,
            )
            for join in catalog.joins
        ]

    def _disconnected_tables(self, required_tables: list[str], joins: list[dict[str, str]]) -> list[str]:
        graph: dict[str, set[str]] = {table: set() for table in required_tables}
        for join in joins:
            left = join.get("from_table", "")
            right = join.get("to_table", "")
            if left in graph and right in graph:
                graph[left].add(right)
                graph[right].add(left)
        start = required_tables[0]
        visited = {start}
        queue = deque([start])
        while queue:
            table = queue.popleft()
            for neighbor in graph.get(table, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return [table for table in required_tables if table not in visited]

    def _needed_path_joins(
        self,
        required_tables: list[str],
        relationships: list[RelationshipInfo],
    ) -> list[dict[str, str]]:
        if len(required_tables) < 2:
            return []
        needed: list[dict[str, str]] = []
        connected = [required_tables[0]]
        for table in required_tables[1:]:
            path = self._shortest_relationship_path(connected[0], table, relationships)
            for left, right in zip(path, path[1:]):
                rel = self._relationship_between(left, right, relationships)
                if rel:
                    join = {
                        "from_table": rel.source_table,
                        "from_column": rel.source_column,
                        "to_table": rel.target_table,
                        "to_column": rel.target_column,
                    }
                    if not any(self._join_key(join) == self._join_key(existing) for existing in needed):
                        needed.append(join)
            if table not in connected:
                connected.append(table)
        return needed

    def _shortest_relationship_path(
        self,
        start: str,
        target: str,
        relationships: list[RelationshipInfo],
    ) -> list[str]:
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
        return []

    def _relationship_between(
        self,
        left: str,
        right: str,
        relationships: list[RelationshipInfo],
    ) -> RelationshipInfo | None:
        return next(
            (
                rel
                for rel in relationships
                if {rel.source_table, rel.target_table} == {left, right}
            ),
            None,
        )

    def _has_join(self, joins: list[dict[str, str]], expected: dict[str, str]) -> bool:
        expected_key = self._join_key(expected)
        return any(self._join_key(join) == expected_key for join in joins)

    def _join_key(self, join: dict[str, str]) -> tuple[str, str, str, str]:
        left = (join.get("from_table", ""), join.get("from_column", ""))
        right = (join.get("to_table", ""), join.get("to_column", ""))
        return (*left, *right) if left <= right else (*right, *left)


sql_plan_join_verifier = SQLPlanJoinVerifier()
