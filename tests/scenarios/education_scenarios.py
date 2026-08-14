from typing import Dict, Any


SCENARIOS = {
    "salary": [
        {
            "question": "میانگین حقوق کارکنان ماه گذشته چقدر بود؟",
            "expected_tables": ["salary_items"],
            "expected_aggregations": ["AVG"],
            "expected_columns": ["net_salary"]
        },
        {
            "question": "بیشترین حقوق پرداختی در سال جاری",
            "expected_tables": ["salary_items"],
            "expected_aggregations": ["MAX"],
            "expected_columns": ["net_salary"]
        },
        {
            "question": "لیست پرداخت‌های بالای ۵۰ میلیون تومان",
            "expected_tables": ["salary_items"],
            "expected_filters": ["net_salary > 50000000"]
        },
        {
            "question": "مقایسه حقوق بخش‌های مختلف",
            "expected_tables": ["salary_items", "employees", "organization_units"],
            "expected_joins": True
        },
        {
            "question": "مجموع حقوق پرداختی هر ماه",
            "expected_tables": ["salary_items"],
            "expected_aggregations": ["SUM"],
            "group_by": ["month"]
        }
    ],
    "employee": [
        {
            "question": "تعداد کارکنان فعال هر بخش",
            "expected_tables": ["employees", "organization_units"],
            "expected_aggregations": ["COUNT"],
            "expected_filters": ["status = 'active'"]
        },
        {
            "question": "کارکنان جدید ماه گذشته",
            "expected_tables": ["employees"],
            "expected_filters": ["hire_date >= ..."]
        },
        {
            "question": "لیست مدیران مدارس",
            "expected_tables": ["employees"],
            "expected_filters": ["position = 'مدیر مدرسه'"]
        },
        {
            "question": "میانگین سابقه خدمت کارکنان",
            "expected_tables": ["employees"],
            "expected_aggregations": ["AVG"]
        },
        {
            "question": "ترکیب جنسیتی کارکنان هر استان",
            "expected_tables": ["employees", "organization_units"],
            "expected_joins": True
        }
    ],
    "student": [
        {
            "question": "تعداد دانش‌آموزان هر مدرسه",
            "expected_tables": ["students", "schools"],
            "expected_aggregations": ["COUNT"],
            "expected_joins": True
        },
        {
            "question": "دانش‌آموزان پایه دوازدهم",
            "expected_tables": ["students"],
            "expected_filters": ["grade = 'دوازدهم'"]
        },
        {
            "question": "مدارس پرجمعیت",
            "expected_tables": ["schools"],
            "expected_aggregations": ["COUNT"]
        },
        {
            "question": "نرخ ثبت‌نام جدید",
            "expected_tables": ["students"],
            "expected_filters": ["enrollment_year = 1402"]
        },
        {
            "question": "دانش‌آموزان فعال استان تهران",
            "expected_tables": ["students", "schools", "organization_units"],
            "expected_filters": ["status = 'active'", "province = 'تهران'"]
        }
    ],
    "organization": [
        {
            "question": "تعداد واحدهای هر استان",
            "expected_tables": ["organization_units"],
            "expected_aggregations": ["COUNT"],
            "group_by": ["province"]
        },
        {
            "question": "ساختار سازمانی وزارتخانه",
            "expected_tables": ["organization_units"],
            "expected_filters": ["parent_id IS NULL"]
        },
        {
            "question": "واحدهای زیرمجموعه استان تهران",
            "expected_tables": ["organization_units"],
            "expected_filters": ["province = 'تهران'"]
        },
        {
            "question": "تعداد کارکنان هر واحد سازمانی",
            "expected_tables": ["organization_units", "employees"],
            "expected_aggregations": ["COUNT"],
            "expected_joins": True
        },
        {
            "question": "مقایسه تعداد مدارس در استان‌ها",
            "expected_tables": ["schools", "organization_units"],
            "expected_aggregations": ["COUNT"],
            "expected_joins": True
        }
    ]
}


def get_scenarios(category: str = None) -> List[Dict]:
    if category and category in SCENARIOS:
        return SCENARIOS[category]
    return [s for scenarios in SCENARIOS.values() for s in scenarios]


def get_scenario_count() -> Dict[str, int]:
    return {k: len(v) for k, v in SCENARIOS.items()}


from typing import List
