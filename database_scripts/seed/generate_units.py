from typing import List, Dict
from database_scripts.seed.persian_data import (
    PROVINCES, CITIES, generate_persian_name
)


def generate_organization_units(count: int = 100) -> List[Dict]:
    units = []
    
    units.append({
        "name": "وزارت آموزش و پرورش",
        "unit_type": "ministry",
        "parent_id": None,
        "province": "تهران",
        "city": "تهران"
    })
    
    province_names = [
        "اداره کل آموزش و پرورش",
        "سازمان پژوهش و برنامه‌ریزی آموزشی",
        "مرکز اطلاعات و فناوری"
    ]
    
    for i, province in enumerate(PROVINCES[:10]):
        for pname in province_names[:1]:
            units.append({
                "name": f"{pname} {province}",
                "unit_type": "province",
                "parent_id": 1,
                "province": province,
                "city": CITIES.get(province, ["مرکز استان"])[0]
            })
    
    unit_id = len(units) + 1
    for province in PROVINCES[:10]:
        cities = CITIES.get(province, ["مرکز استان"])
        for city in cities[:3]:
            province_id = next((i+1 for i, u in enumerate(units) if u["province"] == province and u["unit_type"] == "province"), 2)
            units.append({
                "name": f"اداره آموزش و پرورش {city}",
                "unit_type": "district",
                "parent_id": province_id,
                "province": province,
                "city": city
            })
            unit_id += 1
    
    return units[:count]


def generate_schools(units: List[Dict], count: int = 500) -> List[Dict]:
    schools = []
    
    district_units = [u for u in units if u["unit_type"] == "district"]
    
    school_names = [
        "دبیرستان شهید بهشتی", "دبیرستان فرزانگان", "دبیرستان امام خمینی",
        "دبیرستان نمونه دولتی", "دبیرستان شاهد", "دبستان پیوند",
        "دبستان امید", "دبستان سعادت", "هنرستان فنی", "پیش دانشگاهی"
    ]
    
    for i in range(count):
        unit = random.choice(district_units) if district_units else units[0]
        school_type = random.choice(["دبیرستان", "دبستان", "هنرستان", "نمونه دولتی"])
        
        schools.append({
            "name": f"{random.choice(school_names)} {unit['city']}",
            "school_type": school_type,
            "organization_unit_id": units.index(unit) + 1,
            "capacity": random.randint(200, 500),
            "established_year": random.randint(1360, 1395),
            "address": f"{unit['province']}، {unit['city']}",
            "phone": f"0{random.randint(21, 86)}-{random.randint(1000000, 9999999)}"
        })
    
    return schools


import random
