from typing import Any, Dict, List, Optional
from backend.knowledge.models import (
    CompanyInfo, BusinessDefinition, MetricDefinition,
    BusinessRule, Terminology, CompanyContext
)


class KnowledgeParser:
    @staticmethod
    def parse_company(data: Dict[str, Any]) -> CompanyInfo:
        return CompanyInfo(**data)
    
    @staticmethod
    def parse_definitions(data: List[Dict[str, Any]]) -> List[BusinessDefinition]:
        return [BusinessDefinition(**d) for d in data]
    
    @staticmethod
    def parse_metrics(data: List[Dict[str, Any]]) -> List[MetricDefinition]:
        return [MetricDefinition(**m) for m in data]
    
    @staticmethod
    def parse_rules(data: List[Dict[str, Any]]) -> List[BusinessRule]:
        return [BusinessRule(**r) for r in data]
    
    @staticmethod
    def parse_terminology(data: List[Dict[str, Any]]) -> List[Terminology]:
        return [Terminology(**t) for t in data]
    
    @staticmethod
    def validate_structure(data: Dict[str, Any], expected_keys: List[str]) -> bool:
        return all(key in data for key in expected_keys)
