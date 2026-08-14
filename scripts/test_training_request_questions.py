import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.api.main import app


CASES = [
    ("تعداد درخواست‌های آموزشی را بگو", "training_request_count", 12, ["COUNT", "demo_training_requests"]),
    ("اطلاعات درخواست‌های آموزشی را نشان بده", None, 12, ["demo_training_requests"]),
    ("نام درخواست‌دهنده‌های آموزشی را نشان بده", None, 12, ["requester_name", "demo_training_requests"]),
    ("تعداد درخواست‌های آموزشی فعال را بگو", "training_request_count", 5, ["status = 'active'"]),
    ("تعداد درخواست ها با پست کارمند اداری", "training_request_count", 2, ["requester_role = 'کارمند اداری'"]),
    ("تعداد درخواست ها با requester_role کارمند اداری", "training_request_count", 2, ["requester_role = 'کارمند اداری'"]),
    ("تعداد درخواست ها با سمت مدیر مدرسه", "training_request_count", 3, ["requester_role = 'مدیر مدرسه'"]),
    ("تعداد درخواست ها با نقش معلم", "training_request_count", 2, ["requester_role = 'معلم'"]),
    ("تعداد درخواست ها با نام درخواست‌دهنده مهسا نادری", "training_request_count", 1, ["requester_name = 'مهسا نادری'"]),
    ("تعداد درخواست ها با نوع درخواست دوره امور مالی", "training_request_count", 2, ["request_type = 'دوره امور مالی'"]),
    ("تعداد درخواست ها با کارمند اداری", "training_request_count", 2, ["requester_role = 'کارمند اداری'"]),
    ("تعداد درخواست ها با مدیر مدرسه", "training_request_count", 3, ["requester_role = 'مدیر مدرسه'"]),
    ("تعداد درخواست ها با مرکز فناوری آموزشی", "training_request_count", 3, ["assigned_unit = 'مرکز فناوری آموزشی'"]),
    ("تعداد موارد با کارمند اداری", "training_request_count", 2, ["requester_role = 'کارمند اداری'"]),
    ("اطلاعات موارد با مرکز فناوری آموزشی", None, 3, ["assigned_unit = 'مرکز فناوری آموزشی'"]),
    ("تعداد موارد استان تهران", "training_request_count", 3, ["province = 'تهران'"]),
    ("تعداد موارد شهر تهران", "training_request_count", 2, ["city = 'تهران'"]),
    ("تعداد درخواست های شهر تهران تایید شده", "training_request_count", 1, ["city = 'تهران'", "status = 'approved'"]),
    ("تعداد درخواست های آموزشی با هزینه کمتر از ۸۰ میلیون", "training_request_count", 8, ["estimated_cost < 80000000"]),
    ("تعداد درخواست های آموزشی با هزینه بالای ۵۰ میلیون", "training_request_count", 8, ["estimated_cost > 50000000"]),
    ("تعداد درخواست های آموزشی با هزینه حداقل ۱۰۰ میلیون", "training_request_count", 2, ["estimated_cost >= 100000000"]),
    ("تعداد درخواست های آموزشی استان تهران با هزینه کمتر از ۱۰۰ میلیون", "training_request_count", 1, ["province = 'تهران'", "estimated_cost < 100000000"]),
    ("درخواست‌های آموزشی تایید شده را نشان بده", None, 4, ["status = 'approved'"]),
    ("درخواست‌های آموزشی در انتظار بررسی را نشان بده", None, 2, ["status = 'pending'"]),
    ("تعداد درخواست‌های آموزشی استان تهران را بگو", "training_request_count", 3, ["province = 'تهران'"]),
    ("درخواست‌های آموزشی شهر تهران را نشان بده", None, 2, ["city = 'تهران'"]),
    ("درخواست‌های آموزشی استان اصفهان را نشان بده", None, 2, ["province = 'اصفهان'"]),
    ("تعداد درخواست‌های کارگاه هوش مصنوعی را بگو", "training_request_count", 3, ["request_type = 'کارگاه هوش مصنوعی'"]),
    ("درخواست‌های دوره ضمن خدمت معلمان را نشان بده", None, 2, ["request_type = 'دوره ضمن خدمت معلمان'"]),
    ("درخواست‌های دوره امور مالی را نشان بده", None, 2, ["request_type = 'دوره امور مالی'"]),
    ("تعداد درخواست‌های آموزشی با اولویت بالا را بگو", "training_request_count", 5, ["priority = 'high'"]),
    ("درخواست‌های آموزشی کم‌اولویت را نشان بده", None, 2, ["priority = 'low'"]),
    ("تعداد درخواست‌های آموزشی فعال استان تهران را بگو", "training_request_count", 1, ["status = 'active'", "province = 'تهران'"]),
    ("درخواست‌های کارگاه هوش مصنوعی با اولویت بالا را نشان بده", None, 2, ["request_type = 'کارگاه هوش مصنوعی'", "priority = 'high'"]),
    ("درخواست‌های تایید شده مرکز فناوری آموزشی را نشان بده", None, 2, ["status = 'approved'", "assigned_unit = 'مرکز فناوری آموزشی'"]),
    ("درخواست‌های آموزشی استان تهران با هزینه بیشتر از ۱۰۰ میلیون را نشان بده", None, 2, ["province = 'تهران'", "estimated_cost > 100000000"]),
    ("گران‌ترین درخواست آموزشی کدام است؟", "requester_name", "مهسا نادری", ["ORDER BY demo_training_requests.estimated_cost DESC", "LIMIT 1"]),
    ("ارزان‌ترین درخواست آموزشی کدام است؟", "requester_name", "نسرین هاشمی", ["ORDER BY demo_training_requests.estimated_cost ASC", "LIMIT 1"]),
    ("میانگین هزینه درخواست‌های آموزشی را بگو", "avg_estimated_cost", 70000000, ["AVG"]),
    ("مجموع هزینه درخواست‌های آموزشی تایید شده را بگو", "total_estimated_cost", 335000000, ["SUM", "status = 'approved'"]),
]


def normalize(value):
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def values_equal(actual, expected):
    actual = normalize(actual)
    expected = normalize(expected)
    if isinstance(actual, float) or isinstance(expected, float):
        return abs(float(actual) - float(expected)) < 0.01
    return actual == expected


def main() -> int:
    client = TestClient(app)
    failures = []
    results = []
    for question, field, expected, sql_contains in CASES:
        response = client.post("/query", json={"question": question, "execute": True})
        payload = response.json()
        rows = (payload.get("result") or {}).get("rows") or []
        sql = payload.get("sql") or ""
        case_failures = []
        if response.status_code != 200:
            case_failures.append(f"http={response.status_code}")
        if not payload.get("success"):
            case_failures.append("success=false")
        if not payload.get("valid"):
            case_failures.append("valid=false")
        if payload.get("group") != "training_request":
            case_failures.append(f"group={payload.get('group')}")
        for needle in sql_contains:
            if needle not in sql:
                case_failures.append(f"sql_missing:{needle}")
        if field is None:
            if len(rows) != expected:
                case_failures.append(f"row_count={len(rows)} expected={expected}")
        else:
            actual = rows[0].get(field) if rows else None
            if not values_equal(actual, expected):
                case_failures.append(f"{field}={actual!r} expected={expected!r}")
        item = {
            "question": question,
            "passed": not case_failures,
            "failures": case_failures,
            "sql": sql,
            "rows": rows[:3],
            "row_count": len(rows),
        }
        results.append(item)
        if case_failures:
            failures.append(item)
    print(json.dumps({"total": len(CASES), "failed": len(failures), "results": results}, ensure_ascii=False, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
