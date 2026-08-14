from backend.pipeline.intent import extract_intent


def test_intent_detects_school_without_matching_employee_teacher_alias():
    intent = extract_intent("شماره تلفن دبیرستان شهید بهشتی")

    assert intent.requested_entity == "school"
    assert intent.wants_phone is True
    assert intent.named_school == "دبیرستان شهید بهشتی"


def test_intent_detects_employee_profile_columns_by_national_id():
    intent = extract_intent("کارمند با کد ملی 4871587050 وضعیت و شغل و اسم و فامیل و تمام ستون ها")

    assert intent.requested_entity == "employee"
    assert intent.national_id == "4871587050"
    assert intent.wants_full_profile is True
    assert {"first_name", "last_name", "position", "status", "national_id"}.issubset(
        set(intent.requested_columns)
    )


def test_intent_normalizes_persian_digits_in_national_id():
    intent = extract_intent("اسم و فامیل کارمند با کد ملی ۴۸۷۱۵۸۷۰۵۰")

    assert intent.requested_entity == "employee"
    assert intent.national_id == "4871587050"


def test_intent_detects_student_count_by_province():
    intent = extract_intent("تعداد دانش‌آموزان استان تهران")

    assert intent.requested_entity == "student"
    assert intent.aggregation == "COUNT"
    assert intent.province == "تهران"
