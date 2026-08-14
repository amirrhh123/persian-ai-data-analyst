from pydantic import BaseModel
from typing import List, Optional, Dict


class EntityTerm(BaseModel):
    term: str
    weight: float = 1.0


class ReportGroup(BaseModel):
    id: str
    name: str
    description: str
    linked_tables: List[str] = []
    keywords: List[str] = []
    priority_terms: List[str] = []
    entity_terms: List[EntityTerm] = []
    example_questions: List[str] = []
    domain_terms: List[str] = []
    excluded_topics: List[str] = []


class ReportGroupSearchResult(BaseModel):
    group_id: str
    group_name: str
    confidence: float
    reason: str
    matched_keywords: List[str] = []
    top_candidates: List[Dict] = []


class TwoStageSearchResult(BaseModel):
    group_id: str
    group_name: str
    report_id: str
    report_name: str
    confidence: float
    reason: str


class ReportGroupSyncResponse(BaseModel):
    tenant_id: str
    groups_synced: int
    status: str


class ReportGroupSearchRequest(BaseModel):
    question: str
