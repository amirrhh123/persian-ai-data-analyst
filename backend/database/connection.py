from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from backend.config import get_settings
from typing import Generator, Dict, Any, Optional


class DatabaseConnection:
    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self.SessionLocal = None
    
    def _get_engine(self):
        if self.engine is None:
            self.engine = create_engine(
                self.settings.database_url,
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
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None):
        engine = self._get_engine()
        with engine.connect() as connection:
            statement = text(query) if isinstance(query, str) else query
            if params:
                result = connection.execute(statement, params)
            else:
                result = connection.execute(statement)
            return result
    
    def test_connection(self) -> bool:
        try:
            engine = self._get_engine()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


db_connection = DatabaseConnection()
