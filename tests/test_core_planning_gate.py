from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def _plan(question: str) -> dict:
    response = client.post("/query", json={"question": question, "execute": False})
    assert response.status_code == 200
    return response.json()


def test_core_gate_student_province_uses_student_join_path():
    payload = _plan("تعداد دانش آموزان استان تهران")

    assert payload["success"] is True
    assert payload["group"] == "student"
    assert payload["report"] == "student_list"
    assert payload["valid"] is True
    assert "FROM students" in payload["sql"]
    assert "JOIN schools ON students.school_id = schools.id" in payload["sql"]
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in payload["sql"]
    assert "organization_units.province = 'تهران'" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_core_gate_employee_province_uses_employee_join_path():
    payload = _plan("اطلاعات کارمندان استان تهران")

    assert payload["success"] is True
    assert payload["group"] == "employee"
    assert payload["report"] == "employee_list"
    assert payload["valid"] is True
    assert "FROM employees" in payload["sql"]
    assert "JOIN organization_units ON employees.organization_unit_id = organization_units.id" in payload["sql"]
    assert "organization_units.province = 'تهران'" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_core_gate_school_province_uses_school_join_path():
    payload = _plan("اسم مدارس استان تهران")

    assert payload["success"] is True
    assert payload["group"] == "student"
    assert payload["report"] == "school_statistics"
    assert payload["valid"] is True
    assert "FROM schools" in payload["sql"]
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in payload["sql"]
    assert "organization_units.province = 'تهران'" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_core_gate_new_semantic_table_still_routes_when_question_is_generic():
    payload = _plan("تعداد درخواست های آموزشی با هزینه کمتر از ۸۰ میلیون")

    assert payload["success"] is True
    assert payload["group"] == "training_request"
    assert payload["report"] == "semantic_table_demo_training_requests"
    assert payload["valid"] is True
    assert "FROM demo_training_requests" in payload["sql"]
    assert "estimated_cost < 80000000" in payload["sql"]


def test_core_gate_ambiguous_value_asks_for_clarification_without_sql():
    payload = _plan("تعداد درخواست ها با تهران")

    assert payload["success"] is False
    assert payload["needs_clarification"] is True
    assert payload["valid"] is False
    assert payload["sql"] is None
    assert "تهران" in payload["clarification_question"]
