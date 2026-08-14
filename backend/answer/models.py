from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class AnswerRequest(BaseModel):
    question: str
    result: Dict[str, Any]
    report_name: str = ""
    group_name: str = ""


class AnswerResponse(BaseModel):
    answer: str
    formatted_data: Optional[Dict[str, Any]] = None
    confidence: float = 0.0


class FormattedResult(BaseModel):
    display_type: str
    summary: str
    details: List[Dict[str, Any]] = []
    total: Optional[int] = None
