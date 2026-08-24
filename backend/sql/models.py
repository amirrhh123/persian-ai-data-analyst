from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class SQLPlan(BaseModel):
    required_tables: List[str] = []
    joins: List[Dict[str, str]] = []
    filters: List[Dict[str, str]] = []
    aggregations: List[Dict[str, str]] = []
    selected_columns: List[str] = []
    group_by: List[str] = []
    order_by: Optional[str] = None
    limit: Optional[int] = None
    planning_source: str = "legacy"


class GeneratedSQL(BaseModel):
    sql: str
    explanation: str
    confidence: float
    plan: Optional[SQLPlan] = None
    generation_source: str = "unknown"


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    missing_required_filters: List[Dict[str, str]] = []


class SQLRepairAttempt(BaseModel):
    attempt: int
    sql: str
    strategies: List[str] = []
    validation: ValidationResult


class SQLRepairResult(BaseModel):
    sql: str
    repaired: bool = False
    valid: bool = False
    stopped_reason: str = ""
    attempts: List[SQLRepairAttempt] = []
    validation: ValidationResult


class JoinVerificationResult(BaseModel):
    is_valid: bool = True
    errors: List[str] = []
    warnings: List[str] = []
    missing_tables: List[str] = []
    disconnected_tables: List[str] = []
    suggested_joins: List[Dict[str, str]] = []


class AggregateSafetyResult(BaseModel):
    is_valid: bool = True
    errors: List[str] = []
    warnings: List[str] = []
    expected_operation: Optional[str] = None
    actual_aggregations: List[str] = []
    requires_group_by: bool = False
    requires_order_by: bool = False
    requires_limit: bool = False


class ResultShapeValidationResult(BaseModel):
    is_valid: bool = True
    errors: List[str] = []
    warnings: List[str] = []
    expected_operation: Optional[str] = None
    columns: List[str] = []
    row_count: int = 0
    expected_single_row: bool = False
    expected_numeric_value: bool = False
    missing_requested_columns: List[str] = []
    shape: Optional[str] = None
    allow_empty: bool = True


class SQLRequest(BaseModel):
    question: str


class SQLResponse(BaseModel):
    plan: SQLPlan
    sql: str
    valid: bool
    validation: ValidationResult
    explanation: str = ""
    confidence: float = 0.0
