import random
from typing import List, Dict
from database_scripts.seed.persian_data import (
    generate_persian_national_id, generate_persian_name, generate_hire_date, POSITIONS
)


def generate_employees(unit_count: int = 50, count: int = 20000) -> List[Dict]:
    employees = []
    
    used_national_ids = set()
    
    for i in range(count):
        national_id = generate_persian_national_id()
        while national_id in used_national_ids:
            national_id = generate_persian_national_id()
        used_national_ids.add(national_id)
        
        first_name, last_name = generate_persian_name()
        
        employees.append({
            "national_id": national_id,
            "first_name": first_name,
            "last_name": last_name,
            "organization_unit_id": random.randint(1, unit_count),
            "position": random.choice(POSITIONS),
            "hire_date": generate_hire_date(),
            "status": random.choices(["active", "inactive"], weights=[0.9, 0.1])[0]
        })
    
    return employees


def generate_salary_items(employee_count: int = 20000, count: int = 500000) -> List[Dict]:
    salary_items = []
    
    for i in range(count):
        employee_id = random.randint(1, employee_count)
        year = random.randint(1400, 1403)
        month = random.randint(1, 12)
        
        base_salary = random.randint(30000000, 80000000)
        allowances = random.randint(5000000, 20000000)
        deductions = random.randint(3000000, 10000000)
        net_salary = base_salary + allowances - deductions
        
        salary_items.append({
            "employee_id": employee_id,
            "year": year,
            "month": month,
            "base_salary": base_salary,
            "allowances": allowances,
            "deductions": deductions,
            "net_salary": net_salary,
            "payment_date": f"{year}-{month:02d}-{random.randint(25, 28):02d}"
        })
    
    return salary_items


def generate_ranking_requests(employee_count: int = 20000, count: int = 5000) -> List[Dict]:
    requests = []
    
    ranks = ["معلم", "معلم درجه ۲", "معلم درجه ۱", "کارشناس", "کارشناس ارشد", "سرپرست"]
    types = ["ارتقای رتبه", "تغییر سمت", "انتقال"]
    statuses = ["pending", "approved", "rejected"]
    
    for i in range(count):
        employee_id = random.randint(1, employee_count)
        current_rank_idx = random.randint(0, len(ranks) - 2)
        
        requests.append({
            "employee_id": employee_id,
            "request_date": f"{random.randint(1400, 1403)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "ranking_type": random.choice(types),
            "current_rank": ranks[current_rank_idx],
            "requested_rank": ranks[current_rank_idx + 1],
            "status": random.choices(statuses, weights=[0.4, 0.4, 0.2])[0],
            "review_date": f"{random.randint(1400, 1403)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}" if random.random() > 0.3 else None
        })
    
    return requests


def generate_retirement_records(employee_count: int = 20000, count: int = 2000) -> List[Dict]:
    records = []
    
    types = ["بازنشستگی عادی", "بازنشستگی پیش از موعد", "بازنشستگی استعلاجی"]
    
    for i in range(count):
        employee_id = random.randint(1, employee_count)
        years_of_service = random.randint(20, 35)
        pension = random.randint(25000000, 50000000)
        
        records.append({
            "employee_id": employee_id,
            "retirement_date": f"{random.randint(1395, 1403)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "retirement_type": random.choice(types),
            "years_of_service": years_of_service,
            "pension_amount": pension,
            "reason": "بازنشستگی پس از اتمام سنوات خدمت"
        })
    
    return records


def generate_students(school_count: int = 500, count: int = 300000) -> List[Dict]:
    students = []
    
    used_national_ids = set()
    
    for i in range(count):
        national_id = generate_persian_national_id()
        while national_id in used_national_ids:
            national_id = generate_persian_national_id()
        used_national_ids.add(national_id)
        
        first_name, last_name = generate_persian_name(is_male=random.random() > 0.48)
        
        students.append({
            "national_id": national_id,
            "first_name": first_name,
            "last_name": last_name,
            "school_id": random.randint(1, school_count),
            "grade": random.choice(["دهم", "یازدهم", "دوازدهم"]),
            "enrollment_year": random.randint(1398, 1402),
            "status": random.choices(["active", "inactive"], weights=[0.95, 0.05])[0]
        })
    
    return students
