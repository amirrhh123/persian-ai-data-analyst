from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def _query(question: str) -> dict:
    response = client.post("/query", json={"question": question, "execute": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"]
    return payload


def test_student_question_is_not_routed_to_new_semantic_table():
    payload = _query("تعداد دانش آموزان استان تهران")

    assert payload["group"] == "student"
    assert "students" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_employee_question_is_not_routed_to_new_semantic_table():
    payload = _query("اطلاعات کارمندان استان تهران")

    assert payload["group"] == "employee"
    assert "employees" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_school_question_is_not_routed_to_new_semantic_table():
    payload = _query("اسم مدارس استان تهران")

    assert payload["group"] == "student"
    assert "schools" in payload["sql"]
    assert "demo_training_requests" not in payload["sql"]


def test_new_generic_table_question_still_routes_to_training_requests():
    payload = _query("تعداد موارد استان تهران")

    assert payload["group"] == "training_request"
    assert "demo_training_requests" in payload["sql"]
