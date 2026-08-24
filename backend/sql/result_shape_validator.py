from __future__ import annotations

from numbers import Number
from typing import Any, Optional

from backend.pipeline.intent import NormalizedIntent
from backend.sql.models import ResultShapeValidationResult, SQLPlan
from backend.sql.result_contract import ResultContract


AGGREGATE_OPERATIONS = {"count", "sum", "avg", "min", "max"}
PROFILE_OPERATIONS = {"list", "profile", "lookup"}

# Roadmap suspicious-result guard: a profile/lookup that returns an enormous
# row count did not actually constrain to the requested person/entity.
SUSPICIOUS_PROFILE_ROWS = 1000


class SQLResultShapeValidator:
    def verify(
        self,
        result: dict[str, Any],
        normalized: NormalizedIntent,
        plan: SQLPlan | None = None,
        contract: ResultContract | None = None,
    ) -> ResultShapeValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        columns = [str(column) for column in (result.get("columns") or [])]
        rows = result.get("rows") or []
        row_count = int(result.get("row_count") or len(rows))
        operation = (normalized.operation or "").lower()

        expected_single_row = operation in AGGREGATE_OPERATIONS and not normalized.dimensions
        expected_numeric_value = operation in AGGREGATE_OPERATIONS
        allow_empty = bool(contract.allow_empty) if contract else operation not in AGGREGATE_OPERATIONS

        if expected_single_row and row_count != 1:
            # A scalar aggregate over zero matching groups legitimately yields
            # no row; treat as empty, not as a broken shape (roadmap rule).
            if row_count == 0 and allow_empty:
                warnings.append(
                    "Aggregate returned no rows (no data matched); treated as empty result."
                )
            else:
                errors.append(
                    f"Intent operation is {operation}, but result returned {row_count} rows instead of exactly 1."
                )

        if expected_numeric_value and row_count and not self._has_numeric_value(rows, columns):
            errors.append(f"Intent operation is {operation}, but result has no numeric aggregate value.")

        if (
            contract
            and contract.shape in {"profile", "single_row"}
            and row_count > SUSPICIOUS_PROFILE_ROWS
        ):
            errors.append(
                f"Suspicious cardinality: single-entity lookup returned {row_count} rows."
            )

        if contract and contract.metric_columns and rows:
            null_metrics = self._all_null_columns(rows, columns)
            if null_metrics & set(self._bare(contract.metric_columns)):
                errors.append(
                    "Metric column(s) are NULL for every row: "
                    + ", ".join(sorted(null_metrics & set(self._bare(contract.metric_columns))))
                )

        if operation == "count" and self._looks_like_raw_list(columns, rows):
            errors.append("Count intent returned raw entity rows instead of a count value.")

        if operation in PROFILE_OPERATIONS and self._looks_like_count_only(columns, rows):
            errors.append(f"{operation} intent returned only a count value instead of entity details.")

        dimension_sources: list[str] = [
            *(normalized.dimensions or []),
            *(contract.dimension_columns if contract else []),
        ]
        if dimension_sources and row_count > 0:
            missing_dimensions = [
                dimension
                for dimension in dict.fromkeys(dimension_sources)
                if not self._column_matches(columns, dimension)
            ]
            if missing_dimensions:
                errors.append(
                    "Grouped intent result is missing dimension columns: "
                    + ", ".join(missing_dimensions)
                )

        missing_requested_columns = self._missing_requested_columns(columns, normalized.requested_columns)
        if missing_requested_columns:
            warnings.append(
                "Result is missing requested columns: " + ", ".join(missing_requested_columns)
            )

        if normalized.limit is not None and row_count > normalized.limit:
            errors.append(
                f"Intent requested limit {normalized.limit}, but result returned {row_count} rows."
            )
        if operation == "rank_one" and row_count > 1:
            errors.append("rank_one intent must return at most one row.")

        if plan and plan.limit is not None and row_count > plan.limit:
            errors.append(f"SQL plan limit is {plan.limit}, but result returned {row_count} rows.")

        shape = contract.shape if contract else ("grouped_metric" if dimension_sources and (plan and plan.aggregations) else None)

        return ResultShapeValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            expected_operation=operation or None,
            columns=columns,
            row_count=row_count,
            expected_single_row=expected_single_row,
            expected_numeric_value=expected_numeric_value,
            missing_requested_columns=missing_requested_columns,
            shape=shape,
            allow_empty=allow_empty,
        )

    def _has_numeric_value(self, rows: list[dict[str, Any]], columns: list[str]) -> bool:
        if not rows:
            return False
        first_row = rows[0] or {}
        values = [first_row.get(column) for column in columns] if columns else list(first_row.values())
        return any(isinstance(value, Number) and not isinstance(value, bool) for value in values)

    @staticmethod
    def _bare(names: list[str]) -> set[str]:
        return {str(name).split(".")[-1].lower() for name in names}

    @staticmethod
    def _all_null_columns(rows: list[dict[str, Any]], columns: list[str]) -> set[str]:
        """Columns (by result name) whose every value is None."""
        null_columns: set[str] = set()
        for column in columns:
            values = [row.get(column) for row in rows if isinstance(row, dict)]
            if values and all(value is None for value in values):
                null_columns.add(column.lower())
        return null_columns

    def _looks_like_raw_list(self, columns: list[str], rows: list[dict[str, Any]]) -> bool:
        lowered = {column.lower() for column in columns}
        if lowered & {"row_count", "count", "student_count", "employee_count", "school_count", "total_students"}:
            return False
        return len(columns) > 1 or len(rows) > 1

    def _looks_like_count_only(self, columns: list[str], rows: list[dict[str, Any]]) -> bool:
        if len(columns) != 1 or len(rows) != 1:
            return False
        column = columns[0].lower()
        return column in {"row_count", "count", "student_count", "employee_count", "school_count", "total_students"} or "count" in column

    def _missing_requested_columns(self, columns: list[str], requested_columns: list[str]) -> list[str]:
        missing: list[str] = []
        for requested in requested_columns:
            if requested and not self._column_matches(columns, requested):
                missing.append(requested)
        return missing

    def _column_matches(self, columns: list[str], expected: str) -> bool:
        expected_name = expected.split(".")[-1].lower()
        for column in columns:
            lowered = column.lower()
            if lowered == expected_name or lowered.endswith(f"_{expected_name}") or expected_name in lowered:
                return True
        return False


sql_result_shape_validator = SQLResultShapeValidator()
