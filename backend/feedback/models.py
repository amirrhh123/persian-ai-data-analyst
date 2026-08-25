"""Models for user feedback and aggregate reporting."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    query_id: str = Field(min_length=8, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    rating: Literal["positive", "negative"]
    selected_group: Optional[str] = Field(default=None, max_length=120)
    selected_report: Optional[str] = Field(default=None, max_length=120)
    corrected_group: Optional[str] = Field(default=None, max_length=120)
    corrected_report: Optional[str] = Field(default=None, max_length=120)
    served_table: Optional[str] = Field(default=None, max_length=120)
    corrected_table: Optional[str] = Field(default=None, max_length=120)
    comment: Optional[str] = Field(default=None, max_length=500)


class FeedbackEvent(BaseModel):
    id: str
    query_id: str
    tenant_id: str
    created_at: datetime
    question_fingerprint: str
    question_redacted: str
    rating: Literal["positive", "negative"]
    selected_group: Optional[str] = None
    selected_report: Optional[str] = None
    corrected_group: Optional[str] = None
    corrected_report: Optional[str] = None
    served_table: Optional[str] = None
    corrected_table: Optional[str] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    message: str


class FeedbackSummary(BaseModel):
    tenant_id: str
    total: int = 0
    positive: int = 0
    negative: int = 0
    satisfaction_rate: float = 0.0
    corrections: int = 0
