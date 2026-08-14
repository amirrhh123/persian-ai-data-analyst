from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class QueryRequest(BaseModel):
    sql: str
    timeout: Optional[int] = 30
    max_rows: Optional[int] = 1000


class QueryResult(BaseModel):
    success: bool
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    truncated: bool = False


class ExecutionConfig(BaseModel):
    timeout: int = 30
    max_rows: int = 1000
    allowed_tables: List[str] = []
