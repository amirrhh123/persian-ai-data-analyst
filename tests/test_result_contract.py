"""Offline tests for semantic result contracts (roadmap Change 4)."""

from backend.pipeline.intent import NormalizedIntent, NormalizedIntentFilter
from backend.sql.deterministic_builder import deterministic_sql_builder
from backend.sql.models import SQLPlan
from backend.sql.result_contract import (
    SHAPE_GROUPED_METRIC,
    SHAPE_LIST,
    SHAPE_PROFILE,
    SHAPE_SCALAR,
    build_result_contract,
    infer_location_dimension,
    validate_plan_shape,
)
from backend.sql.result_shape_validator import sql_result_shape_validator


def _intent(**kwargs) -> NormalizedIntent:
    defaults = dict(
        entity="student",
        operation="count",
        confidence=0.95,
    )
    defaults.update(kwargs)
    return NormalizedIntent(**defaults)


def _filter(field, operator="=", value="x"):
    return NormalizedIntentFilter(field=field, operator=operator, value=value)


# ----------------------------------------------------------------------
# Contract inference
# ----------------------------------------------------------------------

def test_count_with_single_location_filter_is_grouped_metric():
    intent = _intent(filters=[_filter("province", "=", "تهران")])
    assert infer_location_dimension(intent) == "organization_units.province"

    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        selected_columns=["STUDENT_COUNT_GROUPED_BY_PROVINCE"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
        group_by=["organization_units.province"],
    )
    contract = build_result_contract(intent, plan)
    assert contract.shape == SHAPE_GROUPED_METRIC
    assert "organization_units.province" in contract.dimension_columns


def test_plain_count_is_scalar():
    intent = _intent()
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )
    contract = build_result_contract(intent, plan)
    assert contract.shape == SHAPE_SCALAR
    assert contract.expected_cardinality == "single"


def test_national_id_lookup_is_profile_with_single_cardinality():
    intent = _intent(operation="profile", filters=[_filter("national_id", "=", "3489881390")])
    plan = SQLPlan(required_tables=["students"], selected_columns=["GENERIC_TABLE_LIST"], limit=1)
    contract = build_result_contract(intent, plan)
    assert contract.shape == SHAPE_PROFILE
    assert contract.expected_cardinality == "single"
    assert contract.allow_empty is True


def test_list_request_allows_empty_and_multiple_rows():
    intent = _intent(operation="list")
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_LIST"],
        limit=1000,
    )
    contract = build_result_contract(intent, plan)
    assert contract.shape == SHAPE_LIST
    assert contract.allow_empty is True


# ----------------------------------------------------------------------
# Pre-execution validation
# ----------------------------------------------------------------------

def test_pre_exec_catches_missing_group_by():
    intent = _intent(
        filters=[_filter("province", "=", "تهران")],
        dimensions=["organization_units.province"],
    )
    contract = build_result_contract(intent, None)
    assert contract is None  # no plan -> no contract

    grouped_plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        selected_columns=["STUDENT_COUNT_GROUPED_BY_PROVINCE"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
        group_by=["organization_units.province"],
    )
    contract = build_result_contract(intent, grouped_plan)
    assert contract.shape == SHAPE_GROUPED_METRIC
    assert validate_plan_shape(grouped_plan, contract) == []

    # Same intent but the plan lost its GROUP BY -> pre-exec must catch it.
    broken_plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
        group_by=[],
    )
    violations = validate_plan_shape(broken_plan, contract)
    assert violations
    assert any("GROUP BY" in v for v in violations)


def test_single_row_contract_rejects_wide_limit():
    """A single-row contract with LIMIT > 1 is a real pre-exec violation."""
    from backend.sql.result_contract import ResultContract

    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_LIST"],
        limit=50,
    )
    contract = ResultContract(shape="profile", expected_cardinality="single", allow_empty=True)
    assert validate_plan_shape(plan, contract)


# ----------------------------------------------------------------------
# Post-execution validation (suspicious results)
# ----------------------------------------------------------------------

def test_count_result_must_be_numeric():
    intent = _intent()
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )
    contract = build_result_contract(intent, plan)
    bad = sql_result_shape_validator.verify(
        {"columns": ["row_count"], "rows": [{"row_count": "many"}], "row_count": 1},
        intent,
        plan,
        contract=contract,
    )
    assert not bad.is_valid

    good = sql_result_shape_validator.verify(
        {"columns": ["row_count"], "rows": [{"row_count": 12}], "row_count": 1},
        intent,
        plan,
        contract=contract,
    )
    assert good.is_valid


def test_grouped_metric_missing_dimension_column_rejected():
    intent = _intent(filters=[_filter("province", "=", "تهران")], dimensions=["organization_units.province"])
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        selected_columns=["STUDENT_COUNT_GROUPED_BY_PROVINCE"],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
        group_by=["organization_units.province"],
    )
    contract = build_result_contract(intent, plan)
    result = {"columns": ["student_count"], "rows": [{"student_count": 5}], "row_count": 1}
    outcome = sql_result_shape_validator.verify(result, intent, plan, contract=contract)
    assert not outcome.is_valid
    assert any("dimension" in err for err in outcome.errors)


def test_null_metric_for_every_row_is_suspicious():
    intent = _intent(operation="count")
    plan = SQLPlan(
        required_tables=["salary_items"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        aggregations=[{"function": "SUM", "column": "salary_items.net_salary"}],
        group_by=["month"],
    )
    contract = build_result_contract(intent, plan)
    assert contract.metric_columns
    result = {
        "columns": ["month", "sum_net_salary"],
        "rows": [{"month": "01", "sum_net_salary": None}, {"month": "02", "sum_net_salary": None}],
        "row_count": 2,
    }
    outcome = sql_result_shape_validator.verify(result, intent, plan, contract=contract)
    assert not outcome.is_valid


def test_genuine_empty_result_is_not_an_error_for_lists():
    intent = _intent(operation="list")
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["GENERIC_TABLE_LIST"],
        limit=1000,
    )
    contract = build_result_contract(intent, plan)
    outcome = sql_result_shape_validator.verify(
        {"columns": [], "rows": [], "row_count": 0},
        intent,
        plan,
        contract=contract,
    )
    assert outcome.is_valid
    assert outcome.allow_empty is True


# ----------------------------------------------------------------------
# Builder integration (grouped token selection)
# ----------------------------------------------------------------------

def test_builder_emits_grouped_token_for_location_count():
    intent = _intent(filters=[_filter("province", "=", "اصفهان")])
    plan = deterministic_sql_builder.build(intent, catalog=None) if False else None
    # Builder requires a catalog; use the real tenant catalog file (offline).
    from backend.semantic.loader import load_tenant_semantic_catalog

    catalog = load_tenant_semantic_catalog("education_ministry")
    plan = deterministic_sql_builder.build(intent, catalog)
    assert plan is not None
    assert "STUDENT_COUNT_GROUPED_BY_PROVINCE" in plan.selected_columns
    assert plan.group_by == ["organization_units.province"]
