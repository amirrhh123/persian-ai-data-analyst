from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def _query(question: str) -> dict:
    response = client.post("/query", json={"question": question, "execute": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["valid"] is True
    assert "demo_training_requests" in payload["sql"]
    assert payload["group"] == "training_request"
    return payload


def test_training_request_total_count():
    payload = _query("تعداد درخواست‌های آموزشی را بگو")

    assert payload["result"]["rows"] == [{"training_request_count": 12}]


def test_training_request_active_count():
    payload = _query("تعداد درخواست‌های آموزشی فعال را بگو")

    assert payload["result"]["rows"] == [{"training_request_count": 5}]
    assert "status = 'active'" in payload["sql"]


def test_training_request_count_by_persian_requester_role_alias():
    payload = _query("تعداد درخواست ها با پست کارمند اداری")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "requester_role = 'کارمند اداری'" in payload["sql"]


def test_training_request_count_by_raw_requester_role_column_name():
    payload = _query("تعداد درخواست ها با requester_role کارمند اداری")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "requester_role = 'کارمند اداری'" in payload["sql"]


def test_training_request_count_by_generic_role_alias():
    payload = _query("تعداد درخواست ها با سمت مدیر مدرسه")

    assert payload["result"]["rows"] == [{"training_request_count": 3}]
    assert "requester_role = 'مدیر مدرسه'" in payload["sql"]


def test_training_request_count_by_generic_requester_name_alias():
    payload = _query("تعداد درخواست ها با نام درخواست‌دهنده مهسا نادری")

    assert payload["result"]["rows"] == [{"training_request_count": 1}]
    assert "requester_name = 'مهسا نادری'" in payload["sql"]


def test_training_request_count_by_generic_request_type_alias():
    payload = _query("تعداد درخواست ها با نوع درخواست دوره امور مالی")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "request_type = 'دوره امور مالی'" in payload["sql"]


def test_training_request_value_driven_role_inference():
    payload = _query("تعداد درخواست ها با کارمند اداری")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "requester_role = 'کارمند اداری'" in payload["sql"]


def test_training_request_value_driven_assigned_unit_inference():
    payload = _query("تعداد درخواست ها با مرکز فناوری آموزشی")

    assert payload["result"]["rows"] == [{"training_request_count": 3}]
    assert "assigned_unit = 'مرکز فناوری آموزشی'" in payload["sql"]
    assert "city = 'ری'" not in payload["sql"]


def test_training_request_table_inference_from_value_for_generic_count_question():
    payload = _query("تعداد موارد با کارمند اداری")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "requester_role = 'کارمند اداری'" in payload["sql"]


def test_training_request_table_inference_from_value_for_generic_list_question():
    payload = _query("اطلاعات موارد با مرکز فناوری آموزشی")

    assert len(payload["result"]["rows"]) == 3
    assert "assigned_unit = 'مرکز فناوری آموزشی'" in payload["sql"]


def test_training_request_ambiguous_unqualified_value_asks_for_clarification():
    response = client.post("/query", json={"question": "تعداد درخواست ها با تهران", "execute": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["needs_clarification"] is True
    assert "تهران" in payload["clarification_question"]
    assert "city" in payload["clarification_question"]
    assert "province" in payload["clarification_question"]
    assert payload["sql"] is None


def test_training_request_labeled_value_infers_table_and_province_filter():
    payload = _query("تعداد موارد استان تهران")

    assert payload["result"]["rows"] == [{"training_request_count": 3}]
    assert "province = 'تهران'" in payload["sql"]


def test_training_request_labeled_value_infers_table_and_city_filter():
    payload = _query("تعداد موارد شهر تهران")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "city = 'تهران'" in payload["sql"]
    assert "province = 'تهران'" not in payload["sql"]


def test_training_request_city_and_status_combined_filters():
    payload = _query("تعداد درخواست های شهر تهران تایید شده")

    assert payload["result"]["rows"] == [{"training_request_count": 1}]
    assert "city = 'تهران'" in payload["sql"]
    assert "status = 'approved'" in payload["sql"]
    assert "province = 'تهران'" not in payload["sql"]


def test_training_request_numeric_less_than_cost_filter():
    payload = _query("تعداد درخواست های آموزشی با هزینه کمتر از ۸۰ میلیون")

    assert payload["result"]["rows"] == [{"training_request_count": 8}]
    assert "estimated_cost < 80000000" in payload["sql"]


def test_training_request_numeric_greater_than_cost_filter():
    payload = _query("تعداد درخواست های آموزشی با هزینه بالای ۵۰ میلیون")

    assert payload["result"]["rows"] == [{"training_request_count": 8}]
    assert "estimated_cost > 50000000" in payload["sql"]


def test_training_request_numeric_minimum_cost_filter():
    payload = _query("تعداد درخواست های آموزشی با هزینه حداقل ۱۰۰ میلیون")

    assert payload["result"]["rows"] == [{"training_request_count": 2}]
    assert "estimated_cost >= 100000000" in payload["sql"]


def test_training_request_location_and_numeric_filters_do_not_duplicate_city():
    payload = _query("تعداد درخواست های آموزشی استان تهران با هزینه کمتر از ۱۰۰ میلیون")

    assert payload["result"]["rows"] == [{"training_request_count": 1}]
    assert "province = 'تهران'" in payload["sql"]
    assert "estimated_cost < 100000000" in payload["sql"]
    assert "city = 'تهران'" not in payload["sql"]


def test_training_request_tehran_count():
    payload = _query("تعداد درخواست‌های آموزشی استان تهران را بگو")

    assert payload["result"]["rows"] == [{"training_request_count": 3}]
    assert "province = 'تهران'" in payload["sql"]


def test_training_request_ai_workshop_count():
    payload = _query("تعداد درخواست‌های کارگاه هوش مصنوعی را بگو")

    assert payload["result"]["rows"] == [{"training_request_count": 3}]
    assert "request_type = 'کارگاه هوش مصنوعی'" in payload["sql"]


def test_training_request_approved_cost_sum():
    payload = _query("مجموع هزینه درخواست‌های آموزشی تایید شده را بگو")

    assert payload["result"]["rows"] == [{"total_estimated_cost": "335000000"}]
    assert "SUM" in payload["sql"]


def test_training_request_highest_cost():
    payload = _query("گران‌ترین درخواست آموزشی کدام است؟")

    row = payload["result"]["rows"][0]
    assert row["requester_name"] == "مهسا نادری"
    assert row["estimated_cost"] == 142000000
    assert "ORDER BY demo_training_requests.estimated_cost DESC" in payload["sql"]
