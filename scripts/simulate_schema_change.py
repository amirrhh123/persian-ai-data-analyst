import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.connection import db_connection


TABLE_NAME = "demo_training_requests"


def table_exists() -> bool:
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = :table_name
        )
    """
    result = db_connection.execute_query(query, {"table_name": TABLE_NAME})
    return bool(result.scalar())


def add_table() -> None:
    engine = db_connection._get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
                    id SERIAL PRIMARY KEY,
                    requester_name VARCHAR(120) NOT NULL,
                    requester_role VARCHAR(80) NOT NULL,
                    request_type VARCHAR(80) NOT NULL,
                    province VARCHAR(80),
                    city VARCHAR(80),
                    priority VARCHAR(40) DEFAULT 'normal',
                    status VARCHAR(40) DEFAULT 'active',
                    assigned_unit VARCHAR(120),
                    estimated_cost BIGINT DEFAULT 0,
                    requested_at DATE NOT NULL DEFAULT CURRENT_DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                ALTER TABLE public.{TABLE_NAME}
                    ADD COLUMN IF NOT EXISTS requester_role VARCHAR(80) NOT NULL DEFAULT 'کارشناس آموزش',
                    ADD COLUMN IF NOT EXISTS city VARCHAR(80),
                    ADD COLUMN IF NOT EXISTS priority VARCHAR(40) DEFAULT 'normal',
                    ADD COLUMN IF NOT EXISTS assigned_unit VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS estimated_cost BIGINT DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS requested_at DATE NOT NULL DEFAULT CURRENT_DATE
                """
            )
        )
        connection.execute(text(f"TRUNCATE TABLE public.{TABLE_NAME} RESTART IDENTITY"))
        connection.execute(
            text(
                f"""
                INSERT INTO public.{TABLE_NAME}
                    (
                        requester_name,
                        requester_role,
                        request_type,
                        province,
                        city,
                        priority,
                        status,
                        assigned_unit,
                        estimated_cost,
                        requested_at
                    )
                VALUES
                    ('علی رضایی', 'مدیر مدرسه', 'دوره ضمن خدمت معلمان', 'تهران', 'تهران', 'high', 'active', 'اداره آموزش نیروی انسانی', 125000000, '2026-07-01'),
                    ('مریم احمدی', 'معاون آموزشی', 'کارگاه هوش مصنوعی', 'اصفهان', 'اصفهان', 'high', 'approved', 'مرکز فناوری آموزشی', 98000000, '2026-07-03'),
                    ('رضا کاظمی', 'کارشناس منطقه', 'آموزش ایمنی مدارس', 'خراسان رضوی', 'مشهد', 'normal', 'active', 'اداره سلامت و ایمنی', 45000000, '2026-07-05'),
                    ('نسرین هاشمی', 'کارمند اداری', 'دوره امور مالی', 'تهران', 'ری', 'low', 'rejected', 'اداره مالی', 22000000, '2026-07-08'),
                    ('پوریا محمدی', 'معلم', 'کارگاه هوش مصنوعی', 'فارس', 'شیراز', 'normal', 'active', 'مرکز فناوری آموزشی', 76000000, '2026-07-10'),
                    ('سارا کریمی', 'مدیر مدرسه', 'دوره مدیریت مدرسه', 'مازندران', 'ساری', 'high', 'approved', 'اداره آموزش مدیران', 64000000, '2026-07-11'),
                    ('حسین مرادی', 'کارشناس آموزش', 'دوره ضمن خدمت معلمان', 'خوزستان', 'اهواز', 'normal', 'pending', 'اداره آموزش نیروی انسانی', 53000000, '2026-07-13'),
                    ('الهام شریفی', 'معاون پرورشی', 'آموزش مشاوره دانش‌آموزی', 'گیلان', 'رشت', 'high', 'active', 'اداره مشاوره و پرورشی', 87000000, '2026-07-15'),
                    ('محمد یوسفی', 'معلم', 'آموزش ایمنی مدارس', 'کرمان', 'کرمان', 'low', 'approved', 'اداره سلامت و ایمنی', 31000000, '2026-07-17'),
                    ('فاطمه موسوی', 'کارمند اداری', 'دوره امور مالی', 'سیستان و بلوچستان', 'زاهدان', 'normal', 'pending', 'اداره مالی', 39000000, '2026-07-19'),
                    ('مهسا نادری', 'مدیر مدرسه', 'کارگاه هوش مصنوعی', 'تهران', 'تهران', 'high', 'approved', 'مرکز فناوری آموزشی', 142000000, '2026-07-20'),
                    ('امیر جعفری', 'کارشناس منطقه', 'دوره مدیریت مدرسه', 'اصفهان', 'کاشان', 'normal', 'active', 'اداره آموزش مدیران', 58000000, '2026-07-21')
                """
            )
        )
        connection.execute(text(f"ANALYZE public.{TABLE_NAME}"))


def drop_table() -> None:
    engine = db_connection._get_engine()
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS public.{TABLE_NAME}"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add or remove a safe demo table to test semantic freshness and auto-update."
    )
    parser.add_argument("action", choices=["add", "drop", "status"])
    args = parser.parse_args()

    if args.action == "add":
        add_table()
        print(f"added: {TABLE_NAME}")
    elif args.action == "drop":
        drop_table()
        print(f"dropped: {TABLE_NAME}")
    else:
        print(f"exists: {str(table_exists()).lower()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
