from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4


class PipelineRequest(BaseModel):
    question: str
    tenant_id: Optional[str] = None
    execute: bool = True
    session_id: Optional[str] = None


class PipelineStep(BaseModel):
    name: str
    status: str
    duration_ms: float = 0.0
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PipelineTrace(BaseModel):
    steps: List[PipelineStep] = []
    total_duration_ms: float = 0.0
    success: bool = True


class SourceCitation(BaseModel):
    source_type: str
    label: str
    identifier: str
    details: Dict[str, Any] = {}


class CitationView(BaseModel):
    scope: str = "query_level"
    database: str
    tenant_id: str
    tables: List[str] = []
    columns: List[str] = []
    sql_preview: Optional[str] = None
    sources: List[SourceCitation] = []


class PipelineErrorDetail(BaseModel):
    code: str
    stage: str
    severity: str = "error"
    message: str
    user_message: Optional[str] = None


class PipelineResponse(BaseModel):
    query_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    success: bool = True
    rejected: bool = False
    rejection_reason: Optional[str] = None
    unsupported: bool = False
    unsupported_reason: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    group: Optional[str] = None
    group_name: Optional[str] = None
    report: Optional[str] = None
    report_name: Optional[str] = None
    sql: Optional[str] = None
    valid: bool = False
    result: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None
    errors: List[str] = []
    error_details: List[PipelineErrorDetail] = []
    intent: Optional[Dict[str, Any]] = None
    explanation: Optional[str] = None
    confidence: Optional[float] = None
    generation_source: Optional[str] = None
    citations: Optional[CitationView] = None
    trace: PipelineTrace = PipelineTrace()
    execution_time_ms: float = 0.0
    session_id: Optional[str] = None
