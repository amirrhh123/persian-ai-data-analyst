from sqlalchemy import create_engine, text

url = "postgresql://postgres:postgres@localhost:5433/persian_ai_db"
engine = create_engine(url)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Connection OK:", result.scalar())
        
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [row[0] for row in result]
        print(f"Tables found: {len(tables)}")
        for t in tables:
            print(f"  - {t}")
except Exception as e:
    print("Error:", e)
