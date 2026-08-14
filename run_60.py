import requests
import json
import time
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).resolve().parent
questions_path = project_root / "tests" / "manual_questions_education_ministry.json"
with questions_path.open(encoding="utf-8") as f:
    questions = json.load(f)

print(f"Running {len(questions)} questions...\n")

results = []
for i, q in enumerate(questions):
    qid = q["id"]
    text = q["question"]
    exp_group = q.get("expected_group", "")
    exp_report = q.get("expected_report", "")
    exp_unsupported = q.get("should_execute", True) is False and "unsupported" in q.get("category", "")
    exp_clarification = q.get("needs_clarification", False)
    exp_rejected = "security" in q.get("category", "")
    
    start = time.time()
    try:
        r = requests.post("http://localhost:8080/query", json={"question": text, "execute": True}, timeout=120)
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
        
        if exp_rejected:
            passed = rejected
        elif exp_unsupported:
            passed = unsupported
        elif exp_clarification or q.get("needs_clarification"):
            passed = needs_clarification
        elif exp_group:
            passed = actual_group == exp_group
        else:
            passed = True
        
        result = {
            "id": qid,
            "question": text,
            "expected_group": exp_group,
            "actual_group": actual_group,
            "expected_report": exp_report,
            "actual_report": actual_report,
            "rejected": rejected,
            "unsupported": unsupported,
            "needs_clarification": needs_clarification,
            "sql_generated": has_sql,
            "sql_valid": valid,
            "rows": rows,
            "time": elapsed,
            "passed": passed
        }
        results.append(result)
        status = "PASS" if passed else "FAIL"
        print(f"[{i+1:2d}/{len(questions)}] {status} {qid:12s} {elapsed:5.1f}s group={actual_group:15s}")
    except Exception as e:
        results.append({"id": qid, "question": text, "error": str(e), "passed": False, "time": 0})
        print(f"[{i+1:2d}/{len(questions)}] ERROR {qid:12s} {str(e)[:50]}")

results_dir = project_root / "tests" / "results"
results_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
timestamped_path = results_dir / f"benchmark_66_{timestamp}.json"
latest_path = results_dir / "latest_66.json"

with open(timestamped_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

with open(latest_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

passed = sum(1 for r in results if r.get("passed"))
print(f"\n{'='*50}")
print(f"RESULT: {passed}/{len(results)} passed ({passed/len(results)*100:.1f}%)")
print(f"{'='*50}")
print(f"Saved: {timestamped_path}")

failed = [r for r in results if not r.get("passed")]
if failed:
    print(f"\nFailed ({len(failed)}):")
    for f in failed:
        print(f"  - {f['id']}: {f['question'][:50]}")
