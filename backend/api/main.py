from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.config import get_settings
from backend.services.llm_service import llm_service
from backend.knowledge.loader import KnowledgeLoader
from backend.knowledge.context_builder import ContextBuilder, ReportContextBuilder
from backend.reports.service import report_service
from backend.reports.models import ReportSearchRequest, ReportSearchResult, ReportSyncResponse
from backend.reports.group_models import (
    ReportGroupSearchRequest, ReportGroupSearchResult, ReportGroupSyncResponse,
    TwoStageSearchResult
)
from backend.reports.intelligence_service import intelligence_service
from backend.reports.group_loader import GroupLoader
from backend.database.sync_service import schema_sync_service
from backend.database.discovery_service import schema_discovery_service
from backend.database.onboarding_service import database_onboarding_service
from backend.database.models import (
    SchemaDiscoveryResponse,
    SchemaDiscoverySnapshot,
    SchemaSyncResponse,
    TableInfo,
    RelationshipInfo,
)
from backend.semantic.models import (
    SemanticActivationResponse,
    SemanticAutoUpdateResponse,
    SemanticBenchmarkResponse,
    SemanticCatalog,
    SemanticFreshnessResponse,
    SemanticLifecycleResponse,
    LightweightGapApplyResponse,
    LightweightGapSuggestionResponse,
    SemanticRollbackResponse,
    SemanticReviewRequest,
    SemanticReviewResponse,
    SemanticSmokeTestGenerationResponse,
    SemanticSmokeTestRunResponse,
    SemanticSuggestionSet,
    SemanticVersionInfo,
)
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.benchmark_service import semantic_benchmark_service
from backend.semantic.lifecycle_service import semantic_lifecycle_service
from backend.semantic.lightweight_gap_service import lightweight_gap_service
from backend.semantic.review_service import semantic_review_service
from backend.semantic.smoke_test_runner import semantic_smoke_test_runner
from backend.semantic.smoke_test_service import semantic_smoke_test_service
from backend.semantic.suggestion_service import semantic_suggestion_service
from backend.security.data_policy import data_sensitivity_policy
from backend.sql.models import SQLRequest, SQLResponse, SQLPlan, ValidationResult
from backend.sql.service import sql_service
from backend.execution.audit import query_audit_logger
from backend.execution.models import QueryRequest, QueryResult
from backend.execution.service import execution_service
from backend.pipeline.models import PipelineRequest, PipelineResponse
from backend.pipeline.query_pipeline import query_pipeline
from backend.pipeline.error_taxonomy import pipeline_error_taxonomy
from backend.value_index.service import value_index_service
from pathlib import Path

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
TENANTS_DIR = Path(__file__).parent.parent.parent / "knowledge" / "tenants"
UI_FILE = Path(__file__).parent / "dashboard.html"
VAZIRMATN_FONT = Path(__file__).parent.parent.parent / "vazirmatn-v33.003" / "fonts" / "webfonts" / "Vazirmatn[wght].woff2"


def load_prompt(name: str) -> str:
    prompt_file = PROMPTS_DIR / name
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""


def get_loader() -> KnowledgeLoader:
    return KnowledgeLoader(TENANTS_DIR / settings.tenant_id)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


class SQLTestRequest(BaseModel):
    question: str


class SQLTestResponse(BaseModel):
    sql: str
    confidence: str
    explanation: str


class KnowledgeContextResponse(BaseModel):
    context: str


class ReportInfo(BaseModel):
    id: str
    name: str
    description: str
    linked_table: str
    group_id: str = ""


class ReportListResponse(BaseModel):
    reports: List[ReportInfo]


class ReportContextResponse(BaseModel):
    context: str


class TableInfoResponse(BaseModel):
    name: str
    columns: List[Dict[str, Any]]
    primary_keys: List[str]
    row_count: int


class SchemaResponse(BaseModel):
    tables: List[TableInfoResponse]
    total_tables: int


class RelationshipResponse(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str


class RelationshipsResponse(BaseModel):
    relationships: List[RelationshipResponse]
    total_relationships: int


@app.get("/health")
async def health_check():
    ollama_connected = await llm_service.is_connected()
    return {
        "status": "ok",
        "mode": "llm_optional" if settings.llm_enabled else "lightweight",
        "llm_enabled": settings.llm_enabled,
        "ollama_connected": ollama_connected,
        "llm_required": False,
    }


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs"
    }


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Executive-friendly overview of the Persian AI query pipeline."""
    return UI_FILE.read_text(encoding="utf-8")


@app.get("/assets/vazirmatn.woff2", response_class=FileResponse, include_in_schema=False)
async def vazirmatn_font():
    return VAZIRMATN_FONT


@app.get("/knowledge/context", response_model=KnowledgeContextResponse)
async def get_knowledge_context():
    try:
        loader = get_loader()
        business_context = loader.load_business()
        builder = ContextBuilder(business_context)
        full_context = builder.build_full_context()
        return KnowledgeContextResponse(context=full_context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading knowledge: {str(e)}")


@app.get("/knowledge/reports", response_model=ReportListResponse)
async def list_reports():
    try:
        loader = get_loader()
        reports = loader.load_all_reports()
        return ReportListResponse(
            reports=[
                ReportInfo(
                    id=r.id,
                    name=r.name,
                    description=r.description,
                    linked_table=r.linked_table,
                    group_id=r.group_id or ""
                ) for r in reports
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading reports: {str(e)}")


@app.get("/knowledge/reports/{report_id}/context", response_model=ReportContextResponse)
async def get_report_context(report_id: str):
    try:
        loader = get_loader()
        report_context = loader.load_report_context(report_id)
        if not report_context:
            raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
        
        builder = ReportContextBuilder(report_context)
        full_context = builder.build_full_context()
        return ReportContextResponse(context=full_context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading report context: {str(e)}")


@app.post("/reports/groups/sync", response_model=ReportGroupSyncResponse)
async def sync_groups():
    try:
        result = intelligence_service.sync_groups(settings.tenant_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing groups: {str(e)}")


@app.post("/reports/sync", response_model=ReportSyncResponse)
async def sync_reports():
    try:
        result = intelligence_service.sync_reports(settings.tenant_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing reports: {str(e)}")


@app.post("/reports/groups/search", response_model=ReportGroupSearchResult)
async def search_groups(request: ReportGroupSearchRequest):
    try:
        from backend.reports.group_retriever import group_retriever
        result = group_retriever.search_groups(settings.tenant_id, request.question)
        return ReportGroupSearchResult(
            group_id=result["group_id"],
            group_name=result["group_name"],
            confidence=result["confidence"],
            reason=result["reason"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching groups: {str(e)}")


@app.post("/reports/search", response_model=TwoStageSearchResult)
async def search_reports_two_stage(request: ReportSearchRequest):
    try:
        result = intelligence_service.search_two_stage(settings.tenant_id, request.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching reports: {str(e)}")


@app.post("/database/sync", response_model=SchemaSyncResponse)
async def sync_database_schema():
    try:
        result = schema_sync_service.sync_schema(settings.tenant_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing database schema: {str(e)}")


@app.get("/database/discovery", response_model=SchemaDiscoverySnapshot)
async def discover_database_schema(sample_size: int = 3, sample_value_limit: int = 8):
    try:
        return schema_discovery_service.discover(
            settings.tenant_id,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering database schema: {str(e)}")


@app.post("/database/discovery/sync", response_model=SchemaDiscoveryResponse)
async def sync_database_discovery(sample_size: int = 3, sample_value_limit: int = 8):
    result = schema_discovery_service.sync_discovery(
        settings.tenant_id,
        sample_size=sample_size,
        sample_value_limit=sample_value_limit,
    )
    schema_sync_result = schema_sync_service.sync_schema(settings.tenant_id)
    if schema_sync_result.status != "success":
        raise HTTPException(status_code=500, detail=f"Error syncing validator schema cache: {schema_sync_result.status}")
    if result.status != "success":
        raise HTTPException(status_code=500, detail=result.status)
    discovery_snapshot = database_onboarding_service.load_snapshot(settings.tenant_id)
    value_index_service.sync(discovery_snapshot)
    return result


@app.get("/database/onboarding-report")
async def get_database_onboarding_report():
    try:
        snapshot = database_onboarding_service.load_snapshot(settings.tenant_id)
        return database_onboarding_service.build_report(snapshot)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building onboarding report: {str(e)}")


@app.get("/database/schema-quality-gate")
async def get_database_schema_quality_gate():
    try:
        snapshot = database_onboarding_service.load_snapshot(settings.tenant_id)
        return database_onboarding_service.quality_gate(snapshot)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running schema quality gate: {str(e)}")


@app.get("/database/schema", response_model=SchemaResponse)
async def get_database_schema():
    try:
        schema = schema_sync_service.load_schema(settings.tenant_id)
        tables = [
            TableInfoResponse(
                name=t.name,
                columns=[col.model_dump() for col in t.columns],
                primary_keys=t.primary_keys,
                row_count=t.row_count or 0
            ) for t in schema.tables
        ]
        return SchemaResponse(
            tables=tables,
            total_tables=len(tables)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading schema: {str(e)}")


@app.get("/database/relationships", response_model=RelationshipsResponse)
async def get_database_relationships():
    try:
        schema = schema_sync_service.load_schema(settings.tenant_id)
        relationships = [
            RelationshipResponse(
                source_table=r.source_table,
                source_column=r.source_column,
                target_table=r.target_table,
                target_column=r.target_column,
                relationship_type=r.relationship_type
            ) for r in schema.relationships
        ]
        return RelationshipsResponse(
            relationships=relationships,
            total_relationships=len(relationships)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading relationships: {str(e)}")


@app.get("/semantic/suggestions", response_model=SemanticSuggestionSet)
async def get_semantic_suggestions():
    try:
        return semantic_suggestion_service.generate(settings.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating semantic suggestions: {str(e)}")


@app.post("/semantic/suggestions/sync", response_model=Dict[str, Any])
async def sync_semantic_suggestions():
    try:
        suggestions, output_path = semantic_suggestion_service.sync(settings.tenant_id)
        return {
            "status": "success",
            "tenant_id": suggestions.tenant_id,
            "source_fingerprint": suggestions.source_fingerprint,
            "tables": len(suggestions.tables),
            "joins": len(suggestions.joins),
            "business_terms": len(suggestions.business_terms),
            "value_mappings": len(suggestions.value_mappings),
            "rules": len(suggestions.rules),
            "output_path": str(output_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing semantic suggestions: {str(e)}")


@app.get("/semantic/smoke-tests", response_model=SemanticSmokeTestGenerationResponse)
async def get_semantic_smoke_tests(max_cases_per_table: int = 5):
    try:
        return semantic_smoke_test_service.generate(
            settings.tenant_id,
            max_cases_per_table=max_cases_per_table,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating semantic smoke tests: {str(e)}")


@app.post("/semantic/smoke-tests/sync", response_model=SemanticSmokeTestGenerationResponse)
async def sync_semantic_smoke_tests(max_cases_per_table: int = 5):
    try:
        return semantic_smoke_test_service.sync(
            settings.tenant_id,
            max_cases_per_table=max_cases_per_table,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing semantic smoke tests: {str(e)}")


@app.post("/semantic/smoke-tests/run", response_model=SemanticSmokeTestRunResponse)
async def run_semantic_smoke_tests(limit: int | None = None, execute: bool = False):
    try:
        return await semantic_smoke_test_runner.run(
            settings.tenant_id,
            limit=limit,
            execute=execute,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running semantic smoke tests: {str(e)}")


@app.get("/semantic/lightweight-readiness", response_model=SemanticSmokeTestRunResponse)
async def get_lightweight_readiness(limit: int | None = None):
    try:
        return await semantic_smoke_test_runner.run(
            settings.tenant_id,
            limit=limit,
            execute=False,
            save=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking lightweight readiness: {str(e)}")


@app.get("/semantic/lightweight-gap-suggestions", response_model=LightweightGapSuggestionResponse)
async def get_lightweight_gap_suggestions(limit: int | None = None):
    try:
        return await lightweight_gap_service.suggest(
            settings.tenant_id,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error suggesting lightweight gaps: {str(e)}")


@app.post("/semantic/lightweight-gap-suggestions/apply", response_model=LightweightGapApplyResponse)
async def apply_lightweight_gap_suggestions(limit: int | None = None, validate_after: bool = True):
    try:
        return await lightweight_gap_service.apply_suggestions(
            settings.tenant_id,
            limit=limit,
            validate_after=validate_after,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying lightweight gap suggestions: {str(e)}")


@app.get("/semantic/validate", response_model=SemanticActivationResponse)
async def validate_semantic_suggestions():
    try:
        return semantic_activation_service.validate_current(settings.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating semantic suggestions: {str(e)}")


@app.post("/semantic/review", response_model=SemanticReviewResponse)
async def apply_semantic_review(request: SemanticReviewRequest):
    try:
        return semantic_review_service.apply_review(request, settings.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying semantic review: {str(e)}")


@app.get("/security/data-policy")
async def get_security_data_policy():
    try:
        return data_sensitivity_policy.policy_report(settings.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading data sensitivity policy: {str(e)}")


@app.get("/errors/taxonomy")
async def get_error_taxonomy():
    return pipeline_error_taxonomy.catalog()


@app.post("/semantic/activate", response_model=SemanticActivationResponse)
async def activate_semantic_suggestions(force: bool = False):
    try:
        result = semantic_activation_service.activate(settings.tenant_id, force=force)
        if result.status == "blocked":
            raise HTTPException(status_code=409, detail=result.model_dump())
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error activating semantic layer: {str(e)}")


@app.get("/semantic/active", response_model=SemanticCatalog)
async def get_active_semantic_catalog():
    try:
        return semantic_activation_service.load_active_catalog(settings.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Active semantic catalog not found: {str(e)}")


@app.get("/semantic/versions", response_model=List[SemanticVersionInfo])
async def list_semantic_versions():
    try:
        return semantic_activation_service.list_versions(settings.tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing semantic versions: {str(e)}")


@app.post("/semantic/rollback/{version_id}", response_model=SemanticRollbackResponse)
async def rollback_semantic_version(version_id: str):
    try:
        result = semantic_activation_service.rollback(version_id, settings.tenant_id)
        if result.status == "not_found":
            raise HTTPException(status_code=404, detail=result.model_dump())
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rolling back semantic version: {str(e)}")


@app.post("/semantic/benchmark", response_model=SemanticBenchmarkResponse)
async def run_semantic_benchmark(min_pass_rate: float = 95.0, limit: int | None = None):
    try:
        return await semantic_benchmark_service.run(
            tenant_id=settings.tenant_id,
            min_pass_rate=min_pass_rate,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running semantic benchmark: {str(e)}")


@app.post("/semantic/lifecycle/run", response_model=SemanticLifecycleResponse)
async def run_semantic_lifecycle(
    min_pass_rate: float = 95.0,
    benchmark_limit: int | None = None,
    force_activate: bool = False,
):
    try:
        return await semantic_lifecycle_service.run(
            tenant_id=settings.tenant_id,
            min_pass_rate=min_pass_rate,
            benchmark_limit=benchmark_limit,
            force_activate=force_activate,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running semantic lifecycle: {str(e)}")


@app.get("/semantic/freshness", response_model=SemanticFreshnessResponse)
async def check_semantic_freshness(sample_size: int = 3, sample_value_limit: int = 8):
    try:
        return semantic_lifecycle_service.check_freshness(
            tenant_id=settings.tenant_id,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking semantic freshness: {str(e)}")


@app.post("/semantic/auto-update", response_model=SemanticAutoUpdateResponse)
async def auto_update_semantic_layer(
    min_pass_rate: float = 95.0,
    benchmark_limit: int | None = None,
    force_activate: bool = False,
):
    try:
        return await semantic_lifecycle_service.ensure_updated(
            tenant_id=settings.tenant_id,
            min_pass_rate=min_pass_rate,
            benchmark_limit=benchmark_limit,
            force_activate=force_activate,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error auto-updating semantic layer: {str(e)}")


@app.post("/sql/generate", response_model=SQLResponse)
async def generate_sql(request: SQLRequest):
    try:
        result = await sql_service.generate_sql(request.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating SQL: {str(e)}")


@app.post("/sql/execute", response_model=QueryResult)
async def execute_sql(request: QueryRequest):
    try:
        result = execution_service.execute(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing SQL: {str(e)}")


@app.get("/sql/audit/summary")
async def get_sql_audit_summary(limit: int = 1000):
    try:
        return query_audit_logger.summarize(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading SQL audit summary: {str(e)}")


@app.post("/query", response_model=PipelineResponse)
async def query(request: PipelineRequest):
    try:
        result = await query_pipeline.execute(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in query pipeline: {str(e)}")


@app.post("/llm/chat", response_model=ChatResponse)
async def llm_chat(request: ChatRequest):
    if not settings.llm_enabled:
        raise HTTPException(status_code=503, detail="LLM/Ollama is disabled. The system is running in lightweight semantic mode.")

    system_prompt = load_prompt("system_fa.txt")
    
    try:
        response = await llm_service.chat(request.message, system_prompt)
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama connection error: {str(e)}")


@app.post("/llm/sql-test", response_model=SQLTestResponse)
async def llm_sql_test(request: SQLTestRequest):
    if not settings.llm_enabled:
        raise HTTPException(status_code=503, detail="LLM/Ollama is disabled. SQL generation uses templates/semantic rules only.")

    system_prompt = load_prompt("sql_generation_fa.txt")
    
    try:
        response = await llm_service.chat(request.question, system_prompt)
        
        import json
        try:
            data = json.loads(response)
            return SQLTestResponse(
                sql=data.get("sql", ""),
                confidence=data.get("confidence", "low"),
                explanation=data.get("explanation", "")
            )
        except json.JSONDecodeError:
            return SQLTestResponse(
                sql="",
                confidence="low",
                explanation=response
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama connection error: {str(e)}")
