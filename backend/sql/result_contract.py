"""Semantic result contracts (roadmap Change 4).

A contract states what a CORRECT answer looks like for an operation - not just
whether SQL executed:

    shape / required_output_columns / dimension_columns /
    expected_cardinality / allow_empty

The planner (deterministic builder) consults the inferred contract so generated
SQL satisfies it, and the result-shape validator uses it after execution.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from backend.pipeline.intent import NormalizedIntent
from backend.sql.models import SQLPlan

SHAPE_SCALAR = "scalar"
SHAPE_SINGLE_ROW = "single_row"
SHAPE_PROFILE = "profile"
SHAPE_LIST = "list"
SHAPE_GROUPED_METRIC = "grouped_metric"
SHAPE_RANKED = "ranked"

_LOCATION_FIELDS = {"province", "city"}
_LOCATION_COLUMN_PREFIX = "organization_units"


class ResultContract(BaseModel):
    shape: str
    required_output_columns: List[str] = Field(default_factory=list)
    dimension_columns: List[str] = Field(default_factory=list)
    metric_columns: List[str] = Field(default_factory=list)
    expected_cardinality: str = "any"  # single | at_most_one | multiple | any
    allow_empty: bool = True


def _aggregation_aliases(plan: SQLPlan) -> List[str]:
    aliases: List[str] = []
    for item in plan.aggregations or []:
        function = str(item.get("function", "")).lower()
        column = str(item.get("column", "*"))
        bare = column.split(".")[-1] if column != "*" else "all"
        aliases.append(f"{function.lower()}_{bare}" if function else bare)
    return aliases


def infer_location_dimension(normalized: NormalizedIntent) -> Optional[str]:
    """Single location filter acts as an implicit grouping dimension.

    Product convention: «تعداد X استان تهران» answers with
    (province, count) so every number carries its group label - consistent
    with the به‌تفکیک presentation used across the product.
    """
    if normalized.operation != "count":
        return None
    location_fields = [
        item.field for item in normalized.filters if item.field in _LOCATION_FIELDS
    ]
    if len(location_fields) != 1 or normalized.dimensions:
        return None
    return f"{_LOCATION_COLUMN_PREFIX}.{location_fields[0]}"


def build_result_contract(
    normalized: NormalizedIntent,
    plan: Optional[SQLPlan],
) -> Optional[ResultContract]:
    """Derive the expected result shape from intent plus the chosen plan."""
    if plan is None:
        return None
    operation = (normalized.operation or "").lower()

    aggregations = plan.aggregations or []
    group_by = plan.group_by or []
    dimensions = list(dict.fromkeys([*(normalized.dimensions or []), *group_by]))

    if operation == "rank_one" or (plan.order_by and plan.limit == 1 and not aggregations):
        return ResultContract(
            shape=SHAPE_RANKED,
            expected_cardinality="at_most_one",
            allow_empty=True,
        )

    if aggregations:
        if dimensions:
            return ResultContract(
                shape=SHAPE_GROUPED_METRIC,
                dimension_columns=dimensions,
                metric_columns=_aggregation_aliases(plan),
                required_output_columns=dimensions,
                expected_cardinality="any",
                allow_empty=True,
            )
        return ResultContract(
            shape=SHAPE_SCALAR,
            metric_columns=_aggregation_aliases(plan),
            expected_cardinality="single",
            allow_empty=False,
        )

    if operation in {"profile", "lookup"}:
        unique_lookup = any(item.field == "national_id" for item in normalized.filters)
        return ResultContract(
            shape=SHAPE_PROFILE,
            required_output_columns=list(normalized.requested_columns or []),
            expected_cardinality="single" if unique_lookup else "at_most_one",
            allow_empty=True,
        )

    if operation == "list" or normalized.wants_list or any(
        str(column).startswith("GENERIC_TABLE_LIST") for column in plan.selected_columns
    ):
        return ResultContract(
            shape=SHAPE_LIST,
            required_output_columns=list(normalized.requested_columns or []),
            expected_cardinality="multiple" if normalized.limit is None else "at_most_one",
            allow_empty=True,
        )

    return ResultContract(
        shape=SHAPE_SINGLE_ROW,
        expected_cardinality="at_most_one",
        allow_empty=True,
    )


def validate_plan_shape(
    plan: SQLPlan,
    contract: Optional[ResultContract],
) -> List[str]:
    """Pre-execution check: does the PLAN promise the contracted shape?"""
    if contract is None:
        return []
    violations: List[str] = []

    if contract.shape == SHAPE_GROUPED_METRIC:
        missing_dimensions = [
            dimension
            for dimension in contract.dimension_columns
            if dimension not in (plan.group_by or [])
        ]
        if missing_dimensions:
            violations.append(
                "GROUP BY ابعاد قرارداد را ندارد: " + ", ".join(missing_dimensions)
            )
        if not plan.aggregations:
            violations.append("قرارداد گروهی نیازمند حداقل یک تابع تجمعی است")

    if contract.shape == SHAPE_SCALAR and (plan.group_by or []):
        violations.append("قرارداد اسکالر نباید GROUP BY داشته باشد")

    if contract.expected_cardinality == "single" and plan.limit not in (None, 1):
        violations.append(f"قرارداد تک‌ردیفی با LIMIT {plan.limit} ناسازگار است")

    return violations
