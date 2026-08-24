from __future__ import annotations

from backend.pipeline.intent import NormalizedIntent
from backend.semantic.models import SemanticCatalog
from backend.sql.models import SQLPlan
from backend.sql.planner import sql_planner
from backend.sql.result_contract import infer_location_dimension


ENTITY_BASE_TABLE = {
    "student": "students",
    "employee": "employees",
    "school": "schools",
    "organization": "organization_units",
    "salary": "salary_items",
    "retirement": "retirement_records",
    "ranking": "ranking_requests",
}

LOCATION_JOIN_TABLES = {
    "student": ["students", "schools", "organization_units"],
    "school": ["schools", "organization_units"],
    "employee": ["employees", "organization_units"],
    "salary": ["salary_items", "employees", "organization_units"],
}

LOCAL_FILTER_COLUMNS = {
    "student": {"national_id", "first_name", "last_name", "status", "grade", "enrollment_year", "school_name"},
    "employee": {"national_id", "first_name", "last_name", "status", "position", "hire_year"},
    "school": {"school_name", "school_type", "capacity", "established_year"},
    "organization": {"organization_unit_name", "province", "city"},
}

FIELD_TO_COLUMN = {
    "school_name": "name",
    "organization_unit_name": "name",
    "capacity": "capacity",
}


class DeterministicSQLBuilder:
    supported_entities = {"student", "employee", "school", "organization"}

    def build(
        self,
        normalized: NormalizedIntent,
        catalog: SemanticCatalog,
    ) -> SQLPlan | None:
        if normalized.confidence < 0.7 or not normalized.entity:
            return None
        if normalized.entity not in self.supported_entities:
            return None
        if self._has_multi_value_filters(normalized):
            return None
        if normalized.entity in {"employee", "school"}:
            return None
        if normalized.entity == "student" and normalized.dimensions:
            return None
        if normalized.entity == "student" and any(item.field == "school_name" for item in normalized.filters):
            return None
        if normalized.entity == "student" and normalized.operation in {"profile", "lookup"}:
            return None
        if normalized.entity == "student" and normalized.operation == "count" and not self._is_simple_student_location_count(normalized):
            return None
        if normalized.entity == "student" and normalized.operation == "list":
            return None
        base_table = ENTITY_BASE_TABLE.get(normalized.entity)
        if not base_table or not catalog.table(base_table):
            return None

        required_tables = self._required_tables(normalized)
        joins = sql_planner.detect_joins(required_tables, self._relationships(catalog))
        filters = self._filters(normalized)

        if normalized.operation == "count":
            dimension = infer_location_dimension(normalized)
            grouped_token = None
            group_by: list[str] = list(normalized.dimensions)
            if dimension and not group_by:
                # Contract-driven grouped shape: counts carry their group label.
                group_by = [dimension]
                field = dimension.split(".")[-1]
                token_suffix = f"GROUPED_BY_{field.upper()}"
                entity_token = {
                    "student": f"STUDENT_COUNT_{token_suffix}",
                    "employee": f"EMPLOYEE_COUNT_{token_suffix}",
                    "school": f"SCHOOL_COUNT_{token_suffix}",
                }.get(normalized.entity)
                grouped_token = entity_token

            selected_columns = (
                [grouped_token] if grouped_token else ["GENERIC_TABLE_COUNT"]
            )
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=selected_columns,
                filters=filters,
                aggregations=[{"function": "COUNT", "column": f"{base_table}.id"}],
                group_by=group_by,
                planning_source="deterministic_normalized_intent",
            )

        if normalized.operation in {"list", "profile", "lookup"}:
            effective_operation = normalized.operation
            if normalized.operation in {"profile", "lookup"} and not self._has_unique_lookup_filter(normalized):
                effective_operation = "list"
            selected_columns = ["GENERIC_TABLE_LIST", *normalized.requested_columns]
            if effective_operation == "profile":
                selected_columns = ["GENERIC_TABLE_LIST"]
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=selected_columns,
                filters=filters,
                order_by=self._order_by(normalized),
                limit=normalized.limit or (1 if effective_operation in {"profile", "lookup"} else 1000),
                planning_source="deterministic_normalized_intent",
            )

        if normalized.operation == "rank_one" and normalized.sort:
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=["GENERIC_TABLE_LIST", *normalized.requested_columns],
                filters=filters,
                order_by=self._order_by(normalized),
                limit=1,
                planning_source="deterministic_normalized_intent",
            )

        return None

    def _has_multi_value_filters(self, normalized: NormalizedIntent) -> bool:
        counts: dict[str, int] = {}
        for item in normalized.filters:
            counts[item.field] = counts.get(item.field, 0) + 1
        return any(count > 1 for field, count in counts.items() if field in {"province", "city"})

    def _has_unique_lookup_filter(self, normalized: NormalizedIntent) -> bool:
        return any(item.field == "national_id" for item in normalized.filters)

    def _is_simple_student_location_count(self, normalized: NormalizedIntent) -> bool:
        """Single province OR city filter - both map to grouped contracts."""
        if normalized.entity != "student" or normalized.operation != "count":
            return False
        fields = [item.field for item in normalized.filters]
        return len(fields) == 1 and fields[0] in {"province", "city"}

    def _required_tables(self, normalized: NormalizedIntent) -> list[str]:
        if any(item.field in {"province", "city"} for item in normalized.filters):
            return LOCATION_JOIN_TABLES.get(normalized.entity or "", [ENTITY_BASE_TABLE[normalized.entity or ""]])
        base_table = ENTITY_BASE_TABLE[normalized.entity or ""]
        if normalized.entity == "student" and any(item.field == "school_name" for item in normalized.filters):
            return ["students", "schools"]
        return [base_table]

    def _relationships(self, catalog: SemanticCatalog):
        from backend.database.models import RelationshipInfo

        return [
            RelationshipInfo(
                source_table=join.from_table,
                source_column=join.from_column,
                target_table=join.to_table,
                target_column=join.to_column,
            )
            for join in catalog.joins
        ]

    def _filters(self, normalized: NormalizedIntent) -> list[dict[str, str]]:
        filters: list[dict[str, str]] = []
        for item in normalized.filters:
            column = FIELD_TO_COLUMN.get(item.field, item.field)
            if item.field in {"province", "city"} and normalized.entity in {"student", "school", "employee", "salary"}:
                column = f"organization_units.{item.field}"
            elif item.field == "school_name" and normalized.entity == "student":
                column = "schools.name"
            elif item.field == "school_name" and normalized.entity == "school":
                column = "schools.name"
            elif item.field == "organization_unit_name":
                column = "organization_units.name"
            filters.append({"column": column, "operator": item.operator, "value": item.value})
        return filters

    def _order_by(self, normalized: NormalizedIntent) -> str | None:
        if not normalized.sort:
            return None
        column = FIELD_TO_COLUMN.get(normalized.sort.column, normalized.sort.column)
        return f"{column} {normalized.sort.direction}"


deterministic_sql_builder = DeterministicSQLBuilder()
