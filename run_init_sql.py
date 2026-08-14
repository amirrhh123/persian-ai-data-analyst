from sqlalchemy import create_engine, text
from pathlib import Path

url = "postgresql://postgres:postgres@localhost:5433/persian_ai_db"
engine = create_engine(url)

sql_file = Path("database_scripts/init_education.sql")
sql_content = sql_file.read_text(encoding="utf-8")

try:
    with engine.connect() as conn:
        conn.execute(text(sql_content))
        conn.commit()
        print("SQL script executed successfully!")
        
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [row[0] for row in result]
        print(f"\nTables created: {len(tables)}")
        for t in tables:
            print(f"  - {t}")
except Exception as e:
    print("Error:", e)
