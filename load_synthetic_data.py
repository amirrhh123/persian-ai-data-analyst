import json
from sqlalchemy import create_engine, text
from pathlib import Path

url = "postgresql://postgres:postgres@localhost:5433/persian_ai_db"
engine = create_engine(url)
data_dir = Path("database_scripts/seed/data")


def load_json(filename):
    with open(data_dir / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def insert_batch(table_name, data, batch_size=5000, unique_columns=None):
    if not data:
        return 0
    
    columns = list(data[0].keys())
    placeholders = ", ".join([f":{col}" for col in columns])
    column_names = ", ".join(columns)
    
    conflict_clause = ""
    if unique_columns:
        conflict_cols = ", ".join(unique_columns)
        conflict_clause = f"ON CONFLICT ({conflict_cols}) DO NOTHING"
    
    sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders}) {conflict_clause}"
    
    total = 0
    skipped = 0
    with engine.connect() as conn:
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]
            try:
                result = conn.execute(text(sql), batch)
                total += len(batch)
            except Exception as e:
                skipped += len(batch)
            if total % 50000 == 0 and total > 0:
                print(f"  Inserted {total:,} rows...")
        conn.commit()
    
    return total, skipped


print("Loading synthetic data into PostgreSQL...\n")

print("1. Loading organization_units...")
org_units = load_json("organization_units.json")
count, skipped = insert_batch("organization_units", org_units)
print(f"   Inserted {count} organization_units\n")

print("2. Loading schools...")
schools = load_json("schools.json")
count, skipped = insert_batch("schools", schools)
print(f"   Inserted {count} schools\n")

print("3. Loading employees...")
employees = load_json("employees.json")
count, skipped = insert_batch("employees", employees, unique_columns=["national_id"])
print(f"   Inserted {count} employees (skipped {skipped} duplicates)\n")

print("4. Loading salary_items...")
salary_items = load_json("salary_items.json")
count, skipped = insert_batch("salary_items", salary_items, batch_size=10000)
print(f"   Inserted {count} salary_items\n")

print("5. Loading ranking_requests...")
ranking_requests = load_json("ranking_requests.json")
count, skipped = insert_batch("ranking_requests", ranking_requests)
print(f"   Inserted {count} ranking_requests\n")

print("6. Loading retirement_records...")
retirement_records = load_json("retirement_records.json")
count, skipped = insert_batch("retirement_records", retirement_records)
print(f"   Inserted {count} retirement_records\n")

print("7. Loading students...")
students = load_json("students.json")
count, skipped = insert_batch("students", students, batch_size=10000, unique_columns=["national_id"])
print(f"   Inserted {count} students (skipped {skipped} duplicates)\n")

print("=" * 50)
print("SUMMARY:")
print("=" * 50)
with engine.connect() as conn:
    for table in ["organization_units", "schools", "employees", "salary_items", "ranking_requests", "retirement_records", "students"]:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = result.scalar()
        print(f"  {table}: {count:,} rows")
print("=" * 50)
print("\nDone! Refresh TablePlus to see the data.")
