from typing import List, Dict, Optional
from pydantic import BaseModel


class BenchmarkCase(BaseModel):
    id: str
    question: str
    category: str
    expected_group: str
    expected_report: str
    expected_tables: List[str]
    expected_operation: str
    expected_aggregations: List[str] = []
    expected_filters: List[str] = []
    expected_joins: bool = False


class BenchmarkDataset:
    def __init__(self):
        self.cases: List[BenchmarkCase] = []
    
    def add_case(self, case: BenchmarkCase):
        self.cases.append(case)
    
    def get_cases(self, category: Optional[str] = None) -> List[BenchmarkCase]:
        if category:
            return [c for c in self.cases if c.category == category]
        return self.cases
    
    def get_categories(self) -> List[str]:
        return list(set(c.category for c in self.cases))
    
    def get_count(self) -> int:
        return len(self.cases)
    
    def get_count_by_category(self) -> Dict[str, int]:
        counts = {}
        for c in self.cases:
            counts[c.category] = counts.get(c.category, 0) + 1
        return counts


def create_education_dataset() -> BenchmarkDataset:
    dataset = BenchmarkDataset()
    
    salary_cases = [
        BenchmarkCase(
            id="salary_001",
            question="میانگین حقوق کارکنان ماه گذشته چقدر بود؟",
            category="salary",
            expected_group="salary",
            expected_report="salary_summary",
            expected_tables=["salary_items"],
            expected_operation="aggregation",
            expected_aggregations=["AVG"]
        ),
        BenchmarkCase(
            id="salary_002",
            question="بیشترین حقوق پرداختی در سال جاری",
            category="salary",
            expected_group="salary",
            expected_report="salary_summary",
            expected_tables=["salary_items"],
            expected_operation="aggregation",
            expected_aggregations=["MAX"]
        ),
        BenchmarkCase(
            id="salary_003",
            question="لیست پرداخت‌های بالای ۵۰ میلیون تومان",
            category="salary",
            expected_group="salary",
            expected_report="salary_summary",
            expected_tables=["salary_items"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="salary_004",
            question="مقایسه حقوق بخش‌های مختلف",
            category="salary",
            expected_group="salary",
            expected_report="salary_comparison",
            expected_tables=["salary_items", "employees", "organization_units"],
            expected_operation="join",
            expected_joins=True
        ),
        BenchmarkCase(
            id="salary_005",
            question="مجموع حقوق پرداختی هر ماه",
            category="salary",
            expected_group="salary",
            expected_report="salary_summary",
            expected_tables=["salary_items"],
            expected_operation="aggregation",
            expected_aggregations=["SUM"]
        ),
    ]
    
    employee_cases = [
        BenchmarkCase(
            id="employee_001",
            question="تعداد کارکنان فعال هر بخش",
            category="employee",
            expected_group="employee",
            expected_report="employee_statistics",
            expected_tables=["employees", "organization_units"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"],
            expected_joins=True
        ),
        BenchmarkCase(
            id="employee_002",
            question="کارکنان جدید ماه گذشته",
            category="employee",
            expected_group="employee",
            expected_report="employee_list",
            expected_tables=["employees"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="employee_003",
            question="لیست مدیران مدارس",
            category="employee",
            expected_group="employee",
            expected_report="employee_list",
            expected_tables=["employees"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="employee_004",
            question="میانگین سابقه خدمت کارکنان",
            category="employee",
            expected_group="employee",
            expected_report="employee_statistics",
            expected_tables=["employees"],
            expected_operation="aggregation",
            expected_aggregations=["AVG"]
        ),
        BenchmarkCase(
            id="employee_005",
            question="ترکیب جنسیتی کارکنان هر استان",
            category="employee",
            expected_group="employee",
            expected_report="employee_statistics",
            expected_tables=["employees", "organization_units"],
            expected_operation="join",
            expected_joins=True
        ),
    ]
    
    student_cases = [
        BenchmarkCase(
            id="student_001",
            question="تعداد دانش‌آموزان هر مدرسه",
            category="student",
            expected_group="student",
            expected_report="school_statistics",
            expected_tables=["students", "schools"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"],
            expected_joins=True
        ),
        BenchmarkCase(
            id="student_002",
            question="دانش‌آموزان پایه دوازدهم",
            category="student",
            expected_group="student",
            expected_report="student_list",
            expected_tables=["students"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="student_003",
            question="مدارس پرجمعیت",
            category="student",
            expected_group="student",
            expected_report="school_statistics",
            expected_tables=["schools"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"]
        ),
        BenchmarkCase(
            id="student_004",
            question="نرخ ثبت‌نام جدید",
            category="student",
            expected_group="student",
            expected_report="student_list",
            expected_tables=["students"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="student_005",
            question="دانش‌آموزان فعال استان تهران",
            category="student",
            expected_group="student",
            expected_report="student_list",
            expected_tables=["students", "schools", "organization_units"],
            expected_operation="join",
            expected_joins=True
        ),
    ]
    
    organization_cases = [
        BenchmarkCase(
            id="org_001",
            question="تعداد واحدهای هر استان",
            category="organization",
            expected_group="organization",
            expected_report="organization_structure",
            expected_tables=["organization_units"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"]
        ),
        BenchmarkCase(
            id="org_002",
            question="ساختار سازمانی وزارتخانه",
            category="organization",
            expected_group="organization",
            expected_report="organization_structure",
            expected_tables=["organization_units"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="org_003",
            question="واحدهای زیرمجموعه استان تهران",
            category="organization",
            expected_group="organization",
            expected_report="organization_structure",
            expected_tables=["organization_units"],
            expected_operation="filter"
        ),
        BenchmarkCase(
            id="org_004",
            question="تعداد کارکنان هر واحد سازمانی",
            category="organization",
            expected_group="organization",
            expected_report="organization_structure",
            expected_tables=["organization_units", "employees"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"],
            expected_joins=True
        ),
        BenchmarkCase(
            id="org_005",
            question="مقایسه تعداد مدارس در استان‌ها",
            category="organization",
            expected_group="organization",
            expected_report="organization_structure",
            expected_tables=["schools", "organization_units"],
            expected_operation="aggregation",
            expected_aggregations=["COUNT"],
            expected_joins=True
        ),
    ]
    
    for case in salary_cases + employee_cases + student_cases + organization_cases:
        dataset.add_case(case)
    
    return dataset
