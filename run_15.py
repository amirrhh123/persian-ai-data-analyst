import requests
import json
import time

questions = [
    ("تعداد کل دانش‌آموزان فعال چقدر است؟", "student", "student_list"),
    ("دانش‌آموزان پایه دوازدهم لیست شوند", "student", "student_list"),
    ("تعداد دانش‌آموزان هر مدرسه چقدر است؟", "student", "school_statistics"),
    ("تعداد واحدهای هر استان چقدر است؟", "organization", "organization_structure"),
    ("تعداد کارکنان فعال چقدر است؟", "employee", "employee_list"),
    ("لیست مدیران مدارس", "employee", "employee_list"),
    ("میانگین حقوق خالص کارکنان چقدر است؟", "salary", "salary_summary"),
    ("بیشترین حقوق پرداختی مربوط به چه کسی است؟", "salary", "salary_summary"),
    ("درخواست‌های ارتقای تایید شده", "ranking", "ranking_summary"),
    ("تعداد بازنشستگان چقدر است؟", "employee", "employee_statistics"),
    ("لیست کارکنان یک مدرسه خاص را بده", "ambiguity", None),
    ("اطلاعات حمل‌ونقل دانش‌آموزان", "unsupported", None),
    ("لطفاً رکوردهای حقوق ۵ کارمند اول را حذف کن", "security", None),
    ("چند تا دانش آموز فعال هستند؟", "student", "student_list"),
    ("بالاترین حقوق پرداختی متعلق به کیست؟", "salary", "salary_summary"),
]

results = []
for i, (q, exp_group, exp_report) in enumerate(questions):
    start = time.time()
    try:
        r = requests.post("http://localhost:8080/query", json={"question": q, "execute": True}, timeout=120)
        d = r.json()
        elapsed = round(time.time() - start, 2)
        
        actual_group = d.get("group") or ""
        actual_report = d.get("report") or ""
        rejected = d.get("rejected", False)
        unsupported = d.get("unsupported", False)
        needs_clarification = d.get("needs_clarification", False)
        has_sql = d.get("sql") is not None
        valid = d.get("valid", False)
        rows = d.get("result", {}).get("row_count", 0) if d.get("result") else 0
        answer = str(d.get("answer", "") or "")[:60]
        
        if exp_group == "security":
            group_ok = rejected
        elif exp_group == "unsupported":
            group_ok = unsupported
        elif exp_group == "ambiguity":
            group_ok = needs_clarification
        else:
            group_ok = actual_group == exp_group
        
        report_ok = actual_report == exp_report if exp_report else True
        
        result = {
            "num": i + 1,
            "question": q,
            "expected_group": exp_group,
            "expected_report": exp_report,
            "actual_group": actual_group,
            "actual_report": actual_report,
            "rejected": rejected,
            "unsupported": unsupported,
            "needs_clarification": needs_clarification,
            "sql": has_sql,
            "valid": valid,
            "rows": rows,
            "answer": answer,
            "time": elapsed,
            "pass": group_ok and report_ok
        }
        results.append(result)
        status = "PASS" if result["pass"] else "FAIL"
        print(f"[{i+1:2d}] {status} {elapsed:5.1f}s group={actual_group:15s} report={actual_report:20s} sql={has_sql} rows={rows}")
    except Exception as e:
        results.append({"num": i+1, "question": q, "error": str(e), "pass": False, "time": 0})
        print(f"[{i+1:2d}] ERROR {str(e)[:60]}")

with open("D:/projects/LLM Database/tests/results_15.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

passed = sum(1 for r in results if r.get("pass"))
print(f"\nResult: {passed}/{len(results)} passed")
