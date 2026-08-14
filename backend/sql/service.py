from typing import Optional
from backend.sql.planner import sql_planner
from backend.sql.generator import sql_generator
from backend.sql.validator import sql_validator
from backend.sql.prompt_builder import prompt_builder
from backend.sql.models import SQLPlan, GeneratedSQL, ValidationResult, SQLResponse
from backend.sql.repair_loop import sql_repair_loop
from backend.database.sync_service import schema_sync_service
from backend.knowledge.loader import KnowledgeLoader
from backend.knowledge.models import Report
from backend.config import get_settings
from pathlib import Path


class SQLService:
    def __init__(self):
        self.settings = get_settings()
        self.tenants_dir = Path(__file__).parent.parent.parent / "knowledge" / "tenants"
    
    def _get_report(self, tenant_id: str, report_id: str = None) -> Optional[Report]:
        if not report_id:
            return None
        
        tenant_path = self.tenants_dir / tenant_id
        loader = KnowledgeLoader(tenant_path)
        reports = loader.load_all_reports()
        
        for report in reports:
            if report.id == report_id:
                return report
        
        return None
    
    def _find_report_by_table(self, tenant_id: str, table_name: str) -> Optional[Report]:
        tenant_path = self.tenants_dir / tenant_id
        loader = KnowledgeLoader(tenant_path)
        reports = loader.load_all_reports()
        
        for report in reports:
            if report.linked_table == table_name:
                return report
        
        return None
    
    async def generate_sql(
        self,
        question: str,
        tenant_id: str = None,
        report_id: str = None
    ) -> SQLResponse:
        if tenant_id is None:
            tenant_id = self.settings.tenant_id
        
        schema = schema_sync_service.load_schema(tenant_id)
        
        plan = sql_planner.create_plan(question, schema, tenant_id=tenant_id)
        
        report = self._get_report(tenant_id, report_id)
        if not report and plan.required_tables:
            report = self._find_report_by_table(tenant_id, plan.required_tables[0])
        
        generated = await sql_generator.generate(plan, schema, report=report, tenant_id=tenant_id)
        
        validation = sql_validator.validate(generated.sql, schema)
        if not validation.is_valid:
            repair = sql_repair_loop.repair(generated.sql, schema, report=report)
            generated.sql = repair.sql
            validation = repair.validation
        
        return SQLResponse(
            plan=plan,
            sql=generated.sql,
            valid=validation.is_valid,
            validation=validation,
            explanation=generated.explanation,
            confidence=generated.confidence
        )
    
    def plan_only(
        self,
        question: str,
        tenant_id: str = None
    ) -> SQLPlan:
        if tenant_id is None:
            tenant_id = self.settings.tenant_id
        
        schema = schema_sync_service.load_schema(tenant_id)
        
        return sql_planner.create_plan(question, schema, tenant_id=tenant_id)
    
    def validate_only(
        self,
        sql: str,
        tenant_id: str = None
    ) -> ValidationResult:
        if tenant_id is None:
            tenant_id = self.settings.tenant_id
        
        schema = schema_sync_service.load_schema(tenant_id)
        
        return sql_validator.validate(sql, schema)


sql_service = SQLService()
