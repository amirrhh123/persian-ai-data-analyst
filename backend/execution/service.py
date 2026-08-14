from backend.execution.audit import query_audit_logger
from backend.execution.connection import execution_connection
from backend.execution.limiter import sql_limiter
from backend.execution.models import QueryRequest, QueryResult


class ExecutionService:
    def __init__(self):
        self.connection = execution_connection
        self.limiter = sql_limiter
        self.audit_logger = query_audit_logger
    
    def execute(self, request: QueryRequest) -> QueryResult:
        validation = self.limiter.validate_for_execution(
            request.sql,
            timeout=request.timeout,
            max_rows=request.max_rows,
        )
        
        if not validation.is_valid:
            self.audit_logger.log(
                sql=request.sql,
                status="rejected",
                errors=validation.errors,
                execution_time_ms=0,
                timeout=request.timeout,
                max_rows=request.max_rows,
            )
            return QueryResult(
                success=False,
                error="; ".join(validation.errors),
                execution_time_ms=0
            )
        
        try:
            result = self.connection.execute_query(
                sql=request.sql,
                timeout=request.timeout,
                max_rows=request.max_rows
            )
            self.audit_logger.log(
                sql=request.sql,
                status="success",
                row_count=result["row_count"],
                execution_time_ms=result["execution_time_ms"],
                truncated=result["truncated"],
                timeout=request.timeout,
                max_rows=request.max_rows,
            )
            
            return QueryResult(
                success=True,
                columns=result["columns"],
                rows=result["rows"],
                row_count=result["row_count"],
                execution_time_ms=result["execution_time_ms"],
                truncated=result["truncated"]
            )
        except Exception as e:
            self.audit_logger.log(
                sql=request.sql,
                status="error",
                errors=[str(e)],
                execution_time_ms=0,
                timeout=request.timeout,
                max_rows=request.max_rows,
            )
            return QueryResult(
                success=False,
                error=str(e),
                execution_time_ms=0
            )


execution_service = ExecutionService()
