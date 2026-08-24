"""Offline tests for required-filter contracts and validation (roadmap Change 2)."""

from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.pipeline.intent import (
    QueryIntent,
    suppress_name_substring_columns,
)
from backend.sql.filter_contract import (
    FilterContract,
    RequiredFilter,
    build_filter_contract,
    normalize_value,
)
from backend.sql.models import SQLPlan
from backend.sql.repair_loop import inject_missing_required_filters
from backend.sql.required_filter_validator import required_filter_validator
from backend.sql.validator import SQLValidator


SCHEMA = DatabaseSchema(
    tables=[
        TableInfo(
            name="students",
            columns=[
                ColumnInfo(name="id", data_type="integer"),
                ColumnInfo(name="first_name", data_type="character varying"),
                ColumnInfo(name="last_name", data_type="character varying"),
                ColumnInfo(name="national_id", data_type="character varying"),
                ColumnInfo(name="grade", data_type="character varying"),
                ColumnInfo(name="status", data_type="character varying"),
                ColumnInfo(name="school_id", data_type="integer"),
            ],
        ),
        TableInfo(
            name="demo_training_requests",
            columns=[
                ColumnInfo(name="id", data_type="integer"),
                ColumnInfo(name="estimated_cost", data_type="numeric"),
                ColumnInfo(name="requester_role", data_type="character varying"),
            ],
        ),
        TableInfo(
            name="schools",
            columns=[
                ColumnInfo(name="id", data_type="integer"),
                ColumnInfo(name="name", data_type="character varying"),
                ColumnInfo(name="school_type", data_type="character varying"),
            ],
        ),
    ]
)


def _contract(*filters: dict) -> FilterContract:
    return FilterContract(filters=[RequiredFilter(**item) for item in filters])


def _validate(sql: str, contract: FilterContract):
    return required_filter_validator.validate(sql, contract, SCHEMA)


# ----------------------------------------------------------------------
# Value normalization
# ----------------------------------------------------------------------

def test_normalize_value_maps_persian_digits_and_strips_quotes():
    assert normalize_value("'۸۰'") == "80"
    assert normalize_value("دبیرستان") == "دبیرستان"


# ----------------------------------------------------------------------
# Roadmap question patterns
# ----------------------------------------------------------------------

def test_person_name_filter_present():
    contract = _contract({"column": "students.first_name", "operator": "=", "value": "پوریا"})
    result = _validate(
        "SELECT COUNT(*) FROM students WHERE students.first_name = 'پوریا'", contract
    )
    assert result.is_valid


def test_person_name_filter_missing_is_rejected():
    contract = _contract({"column": "students.first_name", "operator": "=", "value": "پوریا"})
    result = _validate("SELECT COUNT(*) FROM students", contract)
    assert not result.is_valid
    assert result.missing_required_filters[0]["column"] == "students.first_name"


def test_status_and_location_combination_both_required():
    contract = _contract(
        {"column": "employees.status", "operator": "=", "value": "active"},
        {"column": "organization_units.province", "operator": "=", "value": "تهران"},
    )
    good = _validate(
        "SELECT * FROM employees JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        "WHERE employees.status = 'active' AND organization_units.province = 'تهران'",
        contract,
    )
    bad = _validate(
        "SELECT * FROM employees JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        "WHERE employees.status = 'active'",
        contract,
    )
    assert good.is_valid
    assert not bad.is_valid


def test_national_id_as_text_with_persian_digits_in_sql():
    contract = _contract({"column": "students.national_id", "operator": "=", "value": "3489881390"})
    result = _validate(
        "SELECT * FROM students WHERE students.national_id = '۳۴۸۹۸۸۱۳۹۰'", contract
    )
    assert result.is_valid


def test_grade_plus_school_two_filters():
    contract = _contract(
        {"column": "students.grade", "operator": "=", "value": "یازدهم"},
        {"column": "schools.name", "operator": "=", "value": "دبیرستان شهید بهشتی"},
    )
    sql = (
        "SELECT * FROM students JOIN schools ON students.school_id = schools.id "
        "WHERE students.grade = 'یازدهم' AND schools.name = 'دبیرستان شهید بهشتی'"
    )
    assert _validate(sql, contract).is_valid


def test_numeric_comparison_with_thousand_separators():
    contract = _contract({"column": "estimated_cost", "operator": "<", "value": "80000000"})
    result = _validate(
        "SELECT COUNT(*) FROM demo_training_requests WHERE estimated_cost < 80,000,000",
        contract,
    )
    assert result.is_valid


def test_numeric_comparison_wrong_direction_rejected():
    contract = _contract({"column": "estimated_cost", "operator": "<", "value": "80000000"})
    result = _validate(
        "SELECT COUNT(*) FROM demo_training_requests WHERE estimated_cost > 80000000",
        contract,
    )
    assert not result.is_valid


# ----------------------------------------------------------------------
# Equivalence rules
# ----------------------------------------------------------------------

def test_in_list_satisfies_equality():
    contract = _contract({"column": "students.status", "operator": "=", "value": "active"})
    result = _validate(
        "SELECT * FROM students WHERE students.status IN ('active', 'graduated')",
        contract,
    )
    assert result.is_valid


def test_or_chain_satisfies_equality():
    contract = _contract({"column": "students.status", "operator": "=", "value": "active"})
    result = _validate(
        "SELECT * FROM students WHERE students.status = 'active' OR students.status = 'graduated'",
        contract,
    )
    assert result.is_valid


def test_like_wildcard_satisfies_equality():
    contract = _contract({"column": "schools.name", "operator": "=", "value": "شهید بهشتی"})
    result = _validate(
        "SELECT * FROM schools WHERE schools.name LIKE '%شهید بهشتی%'", contract
    )
    assert result.is_valid


def test_alias_resolution_matches_qualified_contract():
    contract = _contract({"column": "schools.name", "operator": "=", "value": "فرزانگان"})
    result = _validate(
        "SELECT * FROM schools s WHERE s.name = 'فرزانگان'", contract
    )
    assert result.is_valid


def test_bare_contract_column_matches_any_qualifier():
    contract = _contract({"column": "requester_role", "operator": "=", "value": "کارمند اداری"})
    result = _validate(
        "SELECT COUNT(*) FROM demo_training_requests WHERE demo_training_requests.requester_role = 'کارمند اداری'",
        contract,
    )
    assert result.is_valid


# ----------------------------------------------------------------------
# Contract building: subsumption and advisory operators
# ----------------------------------------------------------------------

def test_school_type_inside_school_name_is_subsumed():
    intent = QueryIntent(requested_entity="school")
    intent.school_type = "دبیرستان"
    intent.named_school = "دبیرستان شهید بهشتی"
    plan = SQLPlan(
        required_tables=["schools"],
        filters=[
            {"column": "name", "operator": "=", "value": "دبیرستان شهید بهشتی"},
            {"column": "school_type", "operator": "=", "value": "دبیرستان"},
        ],
    )
    contract = build_filter_contract(intent, plan)
    school_type_filters = [
        item for item in contract.required_filters() if item.bare_column == "school_type"
    ]
    assert not school_type_filters


def test_year_operator_is_advisory_not_blocking():
    intent = QueryIntent()
    plan = SQLPlan(
        required_tables=["salary_items"],
        filters=[{"column": "year", "operator": "YEAR=", "value": "1403"}],
    )
    contract = build_filter_contract(intent, plan)
    result = _validate("SELECT SUM(net_salary) FROM salary_items", contract)
    assert result.is_valid


def test_plan_and_intent_duplicate_collapse_to_one():
    intent = QueryIntent(requested_entity="employee")
    intent.national_id = "8223876400"
    plan = SQLPlan(
        required_tables=["employees"],
        filters=[{"column": "national_id", "operator": "=", "value": "8223876400"}],
    )
    contract = build_filter_contract(intent, plan)
    national_filters = [item for item in contract.filters if item.bare_column == "national_id"]
    assert len(national_filters) == 1


# ----------------------------------------------------------------------
# Name-span suppression on intent
# ----------------------------------------------------------------------

class _FakeColumn:
    def __init__(self, name, aliases):
        self.name = name
        self.aliases = aliases


class _FakeTable:
    def __init__(self, columns):
        self.columns = columns


class _FakeCatalog:
    def __init__(self, tables):
        self.tables = tables


def test_suppression_removes_columns_matched_inside_school_name():
    catalog = _FakeCatalog(
        [_FakeTable([_FakeColumn("school_type", ["دبیرستان", "مقطع"]), _FakeColumn("phone", ["شماره تلفن"])])]
    )
    intent = QueryIntent(requested_entity="student")
    intent.school_type = "دبیرستان"
    intent.named_school = "دبیرستان فرزانگان مرودشت"
    intent.requested_columns = ["school_type", "phone"]

    suppress_name_substring_columns(intent, catalog)

    assert intent.requested_columns == ["phone"]
    assert intent.school_type is None


def test_suppression_keeps_explicit_column_outside_names():
    catalog = _FakeCatalog([_FakeTable([_FakeColumn("school_type", ["نوع مدرسه"])])])
    intent = QueryIntent(requested_entity="school")
    intent.school_type = "دولتی"
    intent.requested_columns = ["school_type"]

    suppress_name_substring_columns(intent, catalog)

    assert intent.requested_columns == ["school_type"]
    assert intent.school_type == "دولتی"


# ----------------------------------------------------------------------
# Repair-loop injection
# ----------------------------------------------------------------------

def test_injection_adds_where_clause_when_missing():
    sql = "SELECT COUNT(*) FROM students"
    updated, changed = inject_missing_required_filters(
        sql,
        SCHEMA,
        [{"column": "students.first_name", "operator": "=", "value": "پوریا"}],
    )
    assert changed
    assert "WHERE students.first_name = 'پوریا'" in updated


def test_injection_appends_to_existing_where():
    sql = "SELECT * FROM students WHERE students.status = 'active'"
    updated, changed = inject_missing_required_filters(
        sql,
        SCHEMA,
        [{"column": "students.grade", "operator": "=", "value": "یازدهم"}],
    )
    assert changed
    assert "AND students.grade = 'یازدهم'" in updated


def test_injection_inserts_before_group_by():
    sql = "SELECT grade, COUNT(*) FROM students GROUP BY grade ORDER BY grade"
    updated, changed = inject_missing_required_filters(
        sql,
        SCHEMA,
        [{"column": "students.status", "operator": "=", "value": "active"}],
    )
    assert changed
    group_position = updated.lower().index("group by")
    where_position = updated.lower().index("where")
    assert where_position < group_position


def test_injection_quotes_national_ids_as_text():
    sql = "SELECT * FROM students"
    updated, _ = inject_missing_required_filters(
        sql,
        SCHEMA,
        [{"column": "students.national_id", "operator": "=", "value": "3489881390"}],
    )
    assert "'3489881390'" in updated


def test_injection_skips_unknown_columns():
    sql = "SELECT * FROM students"
    updated, changed = inject_missing_required_filters(
        sql,
        SCHEMA,
        [{"column": "students.nonexistent", "operator": "=", "value": "x"}],
    )
    assert not changed
    assert updated == sql


def test_full_validator_reports_missing_through_validate():
    validator = SQLValidator()
    contract = build_filter_contract(
        QueryIntent(national_id="8223876400"),
        SQLPlan(required_tables=["students"]),
    )
    # Contract built from bare national_id intent; column key is national_id.
    result = validator.validate(
        "SELECT first_name FROM students",
        SCHEMA,
        contract=FilterContract(
            filters=[RequiredFilter(column="students.national_id", operator="=", value="8223876400")]
        ),
    )
    assert not result.is_valid
    assert result.missing_required_filters
