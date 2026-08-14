from typing import Dict
from database_scripts.seed.generate_units import generate_organization_units, generate_schools
from database_scripts.seed.generate_employees import (
    generate_employees, generate_salary_items, generate_ranking_requests,
    generate_retirement_records, generate_students
)
import json
from pathlib import Path


def seed_all(
    unit_count: int = 100,
    school_count: int = 500,
    employee_count: int = 20000,
    salary_count: int = 500000,
    student_count: int = 300000,
    output_dir: str = "database_scripts/seed/data"
) -> Dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("Generating organization units...")
    units = generate_organization_units(unit_count)
    with open(output_path / "organization_units.json", "w", encoding="utf-8") as f:
        json.dump(units, f, ensure_ascii=False, indent=2)
    
    print("Generating schools...")
    schools = generate_schools(units, school_count)
    with open(output_path / "schools.json", "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)
    
    print("Generating employees...")
    employees = generate_employees(len(units), employee_count)
    with open(output_path / "employees.json", "w", encoding="utf-8") as f:
        json.dump(employees, f, ensure_ascii=False, indent=2)
    
    print("Generating salary items...")
    salary_items = generate_salary_items(employee_count, salary_count)
    with open(output_path / "salary_items.json", "w", encoding="utf-8") as f:
        json.dump(salary_items, f, ensure_ascii=False, indent=2)
    
    print("Generating ranking requests...")
    ranking_requests = generate_ranking_requests(employee_count, 5000)
    with open(output_path / "ranking_requests.json", "w", encoding="utf-8") as f:
        json.dump(ranking_requests, f, ensure_ascii=False, indent=2)
    
    print("Generating retirement records...")
    retirement_records = generate_retirement_records(employee_count, 2000)
    with open(output_path / "retirement_records.json", "w", encoding="utf-8") as f:
        json.dump(retirement_records, f, ensure_ascii=False, indent=2)
    
    print("Generating students...")
    students = generate_students(school_count, student_count)
    with open(output_path / "students.json", "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    
    counts = {
        "organization_units": len(units),
        "schools": len(schools),
        "employees": len(employees),
        "salary_items": len(salary_items),
        "ranking_requests": len(ranking_requests),
        "retirement_records": len(retirement_records),
        "students": len(students)
    }
    
    print("\nGenerated data counts:")
    for table, count in counts.items():
        print(f"  {table}: {count:,}")
    
    return counts


if __name__ == "__main__":
    seed_all()
