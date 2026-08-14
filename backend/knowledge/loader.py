import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.knowledge.models import (
    CompanyInfo, BusinessDefinition, MetricDefinition,
    BusinessRule, Terminology, CompanyContext, Report, ReportContext
)


class KnowledgeLoader:
    def __init__(self, tenant_path: Path):
        self.tenant_path = tenant_path
        self.business_path = tenant_path / "business"
        self.reports_path = tenant_path / "reports"
    
    def load_yaml(self, file_path: Path) -> Optional[Dict[str, Any]]:
        if not file_path.exists():
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def load_company(self) -> Optional[CompanyInfo]:
        data = self.load_yaml(self.business_path / "company.yaml")
        if data:
            return CompanyInfo(**data)
        return None
    
    def load_definitions(self) -> List[BusinessDefinition]:
        data = self.load_yaml(self.business_path / "definitions.yaml")
        if data and "definitions" in data:
            return [BusinessDefinition(**d) for d in data["definitions"]]
        return []
    
    def load_metrics(self) -> List[MetricDefinition]:
        data = self.load_yaml(self.business_path / "metrics.yaml")
        if data and "metrics" in data:
            return [MetricDefinition(**m) for m in data["metrics"]]
        return []
    
    def load_rules(self) -> List[BusinessRule]:
        data = self.load_yaml(self.business_path / "business_rules.yaml")
        if data and "rules" in data:
            return [BusinessRule(**r) for r in data["rules"]]
        return []
    
    def load_terminology(self) -> List[Terminology]:
        data = self.load_yaml(self.business_path / "terminology.yaml")
        if data and "terminology" in data:
            return [Terminology(**t) for t in data["terminology"]]
        return []
    
    def load_business(self) -> CompanyContext:
        return CompanyContext(
            company=self.load_company(),
            definitions=self.load_definitions(),
            metrics=self.load_metrics(),
            rules=self.load_rules(),
            terminology=self.load_terminology()
        )
    
    def load_report(self, report_id: str) -> Optional[Report]:
        report_file = self.reports_path / f"{report_id}.yaml"
        data = self.load_yaml(report_file)
        if data:
            return Report(**data)
        return None
    
    def load_all_reports(self) -> List[Report]:
        if not self.reports_path.exists():
            return []
        
        reports = []
        for report_file in self.reports_path.glob("*.yaml"):
            data = self.load_yaml(report_file)
            if data:
                reports.append(Report(**data))
        return reports
    
    def load_report_context(self, report_id: str) -> Optional[ReportContext]:
        report = self.load_report(report_id)
        if not report:
            return None
        
        all_metrics = self.load_metrics()
        all_rules = self.load_rules()
        
        metrics = [m for m in all_metrics if m.id in report.allowed_metrics]
        rules = [r for r in all_rules if r.id in report.business_rules]
        
        return ReportContext(
            report=report,
            metrics=metrics,
            rules=rules
        )
    
    def load_all(self) -> Dict[str, Any]:
        return {
            "business": self.load_business(),
            "reports": self.load_all_reports()
        }
