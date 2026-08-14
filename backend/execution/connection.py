from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.config import get_settings
from typing import Generator, Optional
import time


class ExecutionConnection:
    def __init__(self, database_url: Optional[str] = None):
        self.settings = get_settings()
        self.database_url = database_url or self.settings.database_url
        self.engine = None
    
    def _get_engine(self):
        if self.engine is None:
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=1,
                connect_args={
                    "options": "-c statement_timeout=30000"
                }
            )
        return self.engine
    
    def execute_query(self, sql: str, timeout: int = 30, max_rows: int = 1000):
        start_time = time.time()
        
        engine = self._get_engine()
        
        with engine.connect() as connection:
            connection = connection.execution_options(
                timeout=timeout
            )
            
            result = connection.execute(text(sql))
            
            columns = list(result.keys())
            rows = []
            row_count = 0
            
            for row in result:
                if row_count >= max_rows:
                    break
                row_dict = {columns[i]: row[i] for i in range(len(columns))}
                rows.append(row_dict)
                row_count += 1
            
            execution_time = (time.time() - start_time) * 1000
            
            return {
                "columns": columns,
                "rows": rows,
                "row_count": row_count,
                "execution_time_ms": round(execution_time, 2),
                "truncated": row_count >= max_rows
            }


execution_connection = ExecutionConnection()
