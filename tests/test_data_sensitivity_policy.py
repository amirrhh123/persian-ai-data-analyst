from backend.security.data_policy import DataSensitivityPolicy


def test_data_policy_masks_sensitive_result_columns(monkeypatch):
    policy = DataSensitivityPolicy()
    monkeypatch.setattr(policy, "sensitive_columns", lambda tenant_id=None: {("employees", "national_id"): "PII"})

    protected = policy.apply_to_result(
        {
            "columns": ["first_name", "national_id", "phone"],
            "rows": [{"first_name": "Nasrin", "national_id": "8223876400", "phone": "02188776655"}],
            "row_count": 1,
        }
    )

    assert protected["rows"][0]["first_name"] == "Nasrin"
    assert protected["rows"][0]["national_id"] == "***6400"
    assert protected["rows"][0]["phone"] == "***6655"
    assert protected["data_policy"]["masked_columns"] == ["national_id", "phone"]


def test_data_policy_masks_salary_like_columns_without_catalog(monkeypatch):
    policy = DataSensitivityPolicy()
    monkeypatch.setattr(policy, "sensitive_columns", lambda tenant_id=None: {})

    protected = policy.apply_to_result(
        {
            "columns": ["employee_name", "net_salary"],
            "rows": [{"employee_name": "Ali", "net_salary": 1000}],
            "row_count": 1,
        }
    )

    assert protected["rows"][0]["net_salary"] == "***"


def test_data_policy_endpoint(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        main.data_sensitivity_policy,
        "policy_report",
        lambda tenant_id=None: {
            "tenant_id": "education_ministry",
            "status": "ok",
            "default_action": "mask",
            "sensitive_columns": [{"table": "employees", "column": "national_id", "reason": "PII"}],
            "rules": [],
        },
    )

    response = TestClient(app).get("/security/data-policy")

    assert response.status_code == 200
    assert response.json()["default_action"] == "mask"
