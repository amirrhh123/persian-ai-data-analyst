from pydantic import BaseModel
from typing import List, Optional


class ReportDocument(BaseModel):
    id: str
    content: str
    metadata: dict


class ReportSearchResult(BaseModel):
    report_id: str
    confidence: float
    reason: str


class ReportSearchRequest(BaseModel):
    question: str


class ReportSyncResponse(BaseModel):
    tenant_id: str
    reports_synced: int
    status: str
