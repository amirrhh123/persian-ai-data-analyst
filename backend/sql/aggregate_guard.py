from __future__ import annotations

from backend.pipeline.intent import NormalizedIntent
from backend.sql.models import AggregateSafetyResult, SQLPlan


AGGREGATE_OPERATIONS = {"count", "sum", "avg", "min", "max"}


class SQLAggregateSafetyGuard:
    def verify(self, plan: SQLPlan, normalized: NormalizedIntent) -> AggregateSafetyResult:
        errors: list[str] = []
        warnings: list[str] = []
        selected = {str(column).upper() for column in plan.selected_columns}
        actual = [str(item.get("function", "")).upper() for item in plan.aggregations if item.get("function")]
        operation = (normalized.operation or "").lower()

        if operation == "count":
            if not self._has_count(plan, selected, actual):
                errors.append("Intent operation is count, but SQL plan does not contain COUNT.")
            if any(column == "*" for column in plan.selected_columns):
                errors.append("Count intent must not select raw '*' columns.")

        if operation in {"list", "profile", "lookup"}:
            if self._has_count(plan, selected, actual) and "GENERIC_TABLE_COUNT" in selected:
                errors.append("List/profile/lookup intent must not use COUNT output.")
            if plan.group_by:
                warnings.append("List/profile/lookup intent has GROUP BY; verify this is intentional.")

        if operation in {"sum", "avg", "min", "max"}:
            expected = operation.upper()
            if expected not in actual and "GENERIC_TABLE_AGGREGATE" not in selected:
                errors.append(f"Intent operation is {operation}, but SQL plan does not contain {expected}.")

        if normalized.dimensions:
            if not plan.group_by:
                errors.append("Intent has grouping dimensions, but SQL plan has no GROUP BY.")
            else:
                missing_dimensions = [dimension for dimension in normalized.dimensions if dimension not in plan.group_by]
                if missing_dimensions:
                    errors.append(f"SQL plan GROUP BY is missing dimensions: {', '.join(missing_dimensions)}")

        requires_order = operation == "rank_one" or bool(normalized.sort)
        if requires_order and not plan.order_by:
            errors.append("Ranking/sorted intent requires ORDER BY.")
        requires_limit = operation == "rank_one" or (normalized.limit is not None and normalized.limit <= 50)
        if requires_limit and not plan.limit:
            errors.append("Ranking/limited intent requires LIMIT.")
        if operation == "rank_one" and plan.limit != 1:
            errors.append("rank_one intent must use LIMIT 1.")

        return AggregateSafetyResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            expected_operation=operation or None,
            actual_aggregations=actual,
            requires_group_by=bool(normalized.dimensions),
            requires_order_by=requires_order,
            requires_limit=requires_limit,
        )

    def _has_count(self, plan: SQLPlan, selected: set[str], actual: list[str]) -> bool:
        if "COUNT" in actual:
            return True
        if "GENERIC_TABLE_COUNT" in selected:
            return True
        return any("COUNT(" in column.upper() for column in plan.selected_columns)


sql_aggregate_safety_guard = SQLAggregateSafetyGuard()
