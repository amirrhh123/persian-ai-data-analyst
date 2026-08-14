import json

from backend.explainability.service import ExplainabilityService
from backend.pipeline.intent import QueryIntent
from backend.sql.models import SQLPlan, ValidationResult


def test_explainability_service_builds_structured_json_and_redacts_national_id():
    explanation = ExplainabilityService().build(
        question="اسم کارمند با کد ملی 8223876400",
        plan=SQLPlan(
            required_tables=["employees"],
            selected_columns=["first_name", "national_id"],
            filters=[{"column": "national_id", "operator": "=", "value": "8223876400"}],
            limit=1,
        ),
        sql="SELECT employees.first_name, employees.national_id FROM employees WHERE employees.national_id = '8223876400'",
        validation=ValidationResult(is_valid=True),
        intent=QueryIntent(requested_entity="employee", national_id="8223876400"),
        result={
            "columns": ["first_name", "national_id"],
            "rows": [{"first_name": "Nasrin", "national_id": "***6400"}],
            "row_count": 1,
            "data_policy": {"masked_columns": ["national_id"]},
        },
        generator_explanation="generated",
    )

    data = json.loads(explanation)
    assert data["table_selection"]["tables"] == ["employees"]
    assert data["filters"][0]["value"] == "***"
    assert data["safety"]["validated"] is True
    assert data["result"]["data_policy"]["masked_columns"] == ["national_id"]


def test_explainability_service_marks_invalid_sql_safety():
    explanation = ExplainabilityService().build(
        question="bad",
        plan=SQLPlan(required_tables=["employees"]),
        sql="DELETE FROM employees",
        validation=ValidationResult(is_valid=False, errors=["not select"]),
    )

    data = json.loads(explanation)
    assert data["safety"]["select_only"] is False
    assert data["safety"]["has_forbidden_write"] is True
    assert data["safety"]["errors"] == ["not select"]
