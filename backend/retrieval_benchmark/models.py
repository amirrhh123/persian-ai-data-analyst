from typing import Literal
from pydantic import BaseModel, Field

class RetrievalBenchmarkCase(BaseModel):
    id: str
    question: str
    expected_group: str
    expected_report: str | None = None
    tags: list[str] = []

class RetrievalBenchmarkRequest(BaseModel):
    top_k: int = Field(default=3, ge=1, le=10)
    minimum_top1: float = Field(default=0.80, ge=0.0, le=1.0)

class RetrievalCaseResult(BaseModel):
    id: str
    question: str
    level: Literal["group", "report"]
    expected: str
    ranked_ids: list[str]
    rank: int | None = None
    passed_top1: bool
    passed_top_k: bool
    latency_ms: float
    error: str | None = None

class RetrievalMetrics(BaseModel):
    evaluated: int
    top1_accuracy: float
    top_k_accuracy: float
    mrr: float
    average_latency_ms: float

class RetrievalBenchmarkResult(BaseModel):
    status: Literal["passed", "failed"]
    tenant_id: str
    top_k: int
    minimum_top1: float
    group: RetrievalMetrics
    report: RetrievalMetrics
    overall_top1_accuracy: float
    cases: list[RetrievalCaseResult]
