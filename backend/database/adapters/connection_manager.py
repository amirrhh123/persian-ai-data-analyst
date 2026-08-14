from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Optional
from backend.config import get_settings


class ConnectionManager:
    def __init__(self, database_url: Optional[str] = None):
        self.settings = get_settings()
        self.database_url = database_url or self.settings.database_url
        self.engine = None
        self.SessionLocal = None
    
    def _get_engine(self):
        if self.engine is None:
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10
            )
        return self.engine
    
    def get_session(self) -> Generator[Session, None, None]:
        engine = self._get_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(self, query: str):
        engine = self._get_engine()
        with engine.connect() as connection:
            result = connection.execute(text(query))
            return result
    
    def test_connection(self) -> bool:
        try:
            engine = self._get_engine()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    def get_table_count(self, table_name: str) -> int:
        try:
            result = self.execute_query(f"SELECT COUNT(*) FROM {table_name}")
            return result.scalar()
        except Exception:
            return 0
    
    def table_exists(self, table_name: str) -> bool:
        try:
            result = self.execute_query(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :name)",
            )
            return result.scalar()
        except Exception:
            return False


connection_manager = ConnectionManager()
