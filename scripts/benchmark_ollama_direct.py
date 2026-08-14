"""Benchmark Ollama as a direct Persian-to-SQL generator.

This intentionally bypasses the application's intent parser, templates, semantic
catalog, reports, groups, and ChromaDB.  The model receives only the physical
database schema and foreign-key relationships.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
import psycopg2


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "tests" / "results"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"
DATABASE_DSN = "postgresql://postgres:postgres@localhost:5433/persian_ai_db"


SCHEMA = """
organization_units(id, name, unit_type, parent_id, province, city, created_at)
employees(id, national_id, first_name, last_name, organization_unit_id, position, hire_date, status, created_at)
salary_items(id, employee_id, year, month, base_salary, allowances, deductions, net_salary, payment_date, created_at)
ranking_requests(id, employee_id, request_date, ranking_type, current_rank, requested_rank, status, review_date, created_at)
retirement_records(id, employee_id, retirement_date, retirement_type, years_of_service, pension_amount, reason, created_at)
schools(id, name, school_type, organization_unit_id, capacity, established_year, address, phone, created_at)
students(id, national_id, first_name, last_name, school_id, grade, enrollment_year, status, created_at)

Foreign keys:
employees.organization_unit_id -> organization_units.id
salary_items.employee_id -> employees.id
ranking_requests.employee_id -> employees.id
retirement_records.employee_id -> employees.id
schools.organization_unit_id -> organization_units.id
students.school_id -> schools.id
organization_units.parent_id -> organization_units.id
""".strip()


CASES = [
    {
        "id": "employee_count_province",
        "question": "تعداد کارمندان استان اصفهان را نشان بده",
        "must": [r"count\s*\(", r"employees", r"organization_units", r"province", r"اصفهان"],
    },
    {
        "id": "student_count_province",
        "question": "تعداد دانش آموزان استان تهران را بگو",
        "must": [r"count\s*\(", r"students", r"schools", r"organization_units", r"province", r"تهران"],
    },
    {
        "id": "student_name_filter",
        "question": "تعداد دانش آموزان تهران که اسم آن ها پوریا هست را بگو",
        "must": [r"count\s*\(", r"students", r"schools", r"organization_units", r"first_name", r"پوریا"],
    },
    {
        "id": "school_names_province",
        "question": "اسم مدارس استان تهران را نشان بده",
        "must": [r"schools", r"organization_units", r"province", r"تهران", r"\.name"],
    },
    {
        "id": "school_phone",
        "question": "شماره تلفن دبیرستان شهید بهشتی را بگو",
        "must": [r"schools", r"phone", r"شهید بهشتی"],
    },
    {
        "id": "employee_full_row_national_id",
        "question": "تمام اطلاعات کارمند با کد ملی 4871587050 را نشان بده",
        "must": [r"employees", r"national_id", r"4871587050"],
    },
    {
        "id": "student_count_named_school",
        "question": "تعداد دانش آموزان مدرسه دبیرستان نمونه دولتی اصفهان را بگو",
        "must": [r"count\s*\(", r"students", r"schools", r"نمونه دولتی اصفهان"],
    },
    {
        "id": "student_multi_filter",
        "question": "کد ملی دانش آموز پوریا محمدی پایه یازدهم در مدرسه میناب را بگو",
        "must": [r"students", r"schools", r"national_id", r"first_name", r"last_name", r"grade", r"یازدهم", r"میناب"],
    },
    {
        "id": "employee_lowest_pension",
        "question": "برای کدام کارمند کمترین سنوات پرداخت شده؟",
        "must": [r"retirement_records", r"employees", r"pension_amount", r"order\s+by", r"asc", r"limit\s+1"],
    },
    {
        "id": "employee_pension_by_national_id",
        "question": "سنوات کارمند با کد ملی 2475429291 را بگو",
        "must": [r"retirement_records", r"employees", r"pension_amount", r"national_id", r"2475429291"],
    },
    {
        "id": "salary_combined_filters",
        "question": "میانگین حقوق خالص کارمندان فعال استان تهران در سال ۱۴۰۲ را بگو",
        "must": [r"avg\s*\(", r"salary_items", r"employees", r"organization_units", r"net_salary", r"status", r"active", r"province", r"تهران", r"1402"],
    },
    {
        "id": "ranking_latest",
        "question": "آخرین درخواست رتبه بندی کارمند با کد ملی 8223876400 و وضعیت آن را نشان بده",
        "must": [r"ranking_requests", r"employees", r"national_id", r"8223876400", r"status", r"order\s+by", r"desc", r"limit\s+1"],
    },
]


SYSTEM_PROMPT = """You are a PostgreSQL expert. Convert the Persian question to exactly one read-only SELECT query.
Use only the supplied physical schema and foreign keys. Never invent a table or column.
Return SQL only, with no Markdown, explanation, or comments. Preserve text identifiers such as national IDs as quoted strings.
When the user asks for all information, return all columns of the main entity. Use explicit joins required by the schema.
"""


def normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def clean_sql(text: str) -> str:
    text = re.sub(r"^```(?:sql)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    return normalize_digits(text)


def generate_sql(client: httpx.Client, question: str) -> tuple[str, float]:
    prompt = f"Physical schema:\n{SCHEMA}\n\nPersian question:\n{question}"
    started = time.perf_counter()
    response = client.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0, "top_p": 0.9},
        },
    )
    response.raise_for_status()
    elapsed = time.perf_counter() - started
    return clean_sql(response.json()["message"]["content"]), elapsed


def execute_read_only(connection, sql: str) -> tuple[bool, str, int | None]:
    if not re.match(r"^\s*(select|with)\b", sql, flags=re.IGNORECASE):
        return False, "Output is not a SELECT/CTE query", None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '10s'")
            cursor.execute(sql)
            rows = cursor.fetchmany(5)
            row_count = len(rows)
        connection.rollback()
        return True, "", row_count
    except Exception as exc:  # benchmark must retain individual failures
        connection.rollback()
        return False, str(exc), None


def structural_score(sql: str, patterns: list[str]) -> tuple[bool, list[str]]:
    missing = [pattern for pattern in patterns if not re.search(pattern, sql, flags=re.IGNORECASE)]
    return not missing, missing


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with httpx.Client(timeout=120) as client, psycopg2.connect(DATABASE_DSN) as connection:
        connection.autocommit = False
        for case in CASES:
            try:
                sql, elapsed = generate_sql(client, case["question"])
                structurally_correct, missing = structural_score(sql, case["must"])
                executable, execution_error, sample_row_count = execute_read_only(connection, sql)
            except Exception as exc:
                sql, elapsed = "", 0.0
                structurally_correct, missing = False, case["must"]
                executable, execution_error, sample_row_count = False, str(exc), None
            result = {
                "id": case["id"],
                "question": case["question"],
                "sql": sql,
                "structurally_correct": structurally_correct,
                "missing_expectations": missing,
                "executable": executable,
                "execution_error": execution_error,
                "sample_rows_returned": sample_row_count,
                "latency_seconds": round(elapsed, 2),
            }
            results.append(result)
            print(f"[{case['id']}] semantic={structurally_correct} executable={executable} time={elapsed:.1f}s")

    summary = {
        "model": MODEL,
        "mode": "direct model; physical schema + foreign keys only",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "structurally_correct": sum(item["structurally_correct"] for item in results),
        "executable": sum(item["executable"] for item in results),
        "results": results,
    }
    output = RESULTS_DIR / f"ollama_direct_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT_FILE={output}")
    print(json.dumps({key: summary[key] for key in ("total", "structurally_correct", "executable")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
