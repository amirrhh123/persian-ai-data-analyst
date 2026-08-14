from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class CompanyInfo(BaseModel):
    name: str
    industry: str
    description: Optional[str] = None
    established: Optional[str] = None
    locations: List[str] = []
    departments: List[str] = []


class BusinessDefinition(BaseModel):
    id: str
    term: str
    definition: str
    category: Optional[str] = None


class MetricDefinition(BaseModel):
    id: str
    name: str
    formula: str
    unit: Optional[str] = None
    target: Optional[str] = None
    frequency: Optional[str] = None


class BusinessRule(BaseModel):
    id: str
    name: str
    description: str
    condition: Optional[str] = None
    action: Optional[str] = None
    priority: Optional[str] = None


class Terminology(BaseModel):
    term: str
    meaning: str
    synonyms: List[str] = []


class CompanyContext(BaseModel):
    company: Optional[CompanyInfo] = None
    definitions: List[BusinessDefinition] = []
    metrics: List[MetricDefinition] = []
    rules: List[BusinessRule] = []
    terminology: List[Terminology] = []


class ReportColumnDefinition(BaseModel):
    meaning: str
    persian_name: Optional[str] = None
    data_type: Optional[str] = None
    examples: List[str] = []


class SQLHint(BaseModel):
    default_filters: List[str] = []
    preferred_joins: List[str] = []
    aggregate_columns: List[str] = []
    group_by_columns: List[str] = []


class Report(BaseModel):
    id: str
    name: str
    description: str
    linked_table: str
    group_id: Optional[str] = None
    allowed_metrics: List[str] = []
    business_rules: List[str] = []
    example_questions: List[str] = []
    important_columns: Dict[str, ReportColumnDefinition] = {}
    sql_hints: Optional[SQLHint] = None


class ReportContext(BaseModel):
    report: Report
    metrics: List[MetricDefinition] = []
    rules: List[BusinessRule] = []
