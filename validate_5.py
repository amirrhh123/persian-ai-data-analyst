import requests
import json
import time

questions = [
    ("حذف رکوردهای حقوق", "rejected"),
    ("لیست کارکنان یک مدرسه خاص را بده", "needs_clarification"),
    ("اطلاعات حمل‌ونقل دانش‌آموزان", "unsupported"),
    ("دانش‌آموزان پایه دوازدهم", "group=student"),
    ("تعداد واحدهای هر استان", "group=organization"),
]

for q, expected in questions:
    try:
        r = requests.post("http://localhost:8080/query", json={"question": q, "execute": True}, timeout=120)
        d = r.json()
        print("Q:", q)
        print("  rejected:", d.get("rejected"))
        print("  unsupported:", d.get("unsupported"))
        print("  needs_clarification:", d.get("needs_clarification"))
        print("  group:", d.get("group"))
        print("  sql:", d.get("sql") is not None)
        print("  rows:", d.get("result", {}).get("row_count", 0) if d.get("result") else 0)
        print("  answer:", str(d.get("answer", ""))[:80])
        print("  Expected:", expected)
        print()
    except Exception as e:
        print("Q:", q, "-> ERROR:", e)
