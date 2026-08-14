import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from pathlib import Path
from backend.api.main import app, load_prompt
from backend.config import get_settings, Settings
from backend.services.llm_service import LLMService, llm_service
from backend.knowledge.loader import KnowledgeLoader
from backend.knowledge.context_builder import ContextBuilder, ReportContextBuilder
from backend.knowledge.models import (
    CompanyInfo, BusinessDefinition, MetricDefinition,
    BusinessRule, Terminology, CompanyContext, Report, ReportContext
)


client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TENANT_DIR = Path(__file__).parent.parent / "knowledge" / "tenants" / "retail_company"
BUSINESS_DIR = TENANT_DIR / "business"
REPORTS_DIR = TENANT_DIR / "reports"


# Phase 0 tests
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ollama_connected" in data


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "docs" in data


def test_config_loading():
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.app_name == "Persian AI Data Analyst"
    assert settings.app_version == "0.1.0"


def test_config_defaults():
    settings = Settings()
    assert settings.debug is True
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8080


# Phase 1 tests - Config
def test_ollama_config():
    settings = get_settings()
    assert settings.ollama_host == "http://localhost"
    assert settings.ollama_port == 11434
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.ollama_timeout == 60
    assert settings.ollama_temperature == 0.1
    assert settings.ollama_top_p == 0.9


def test_ollama_url_property():
    settings = get_settings()
    assert settings.ollama_url == "http://localhost:11434"


def test_tenant_config():
    settings = get_settings()
    assert settings.tenant_id in ("retail_company", "education_ministry")


# Phase 1 tests - Prompt loading
def test_load_system_prompt():
    prompt = load_prompt("system_fa.txt")
    assert "دستیار تحلیل داده سازمانی فارسی" in prompt
    assert "فارسی" in prompt


def test_load_sql_prompt():
    prompt = load_prompt("sql_generation_fa.txt")
    assert "متخصص SQL فارسی" in prompt
    assert "SELECT" in prompt


def test_load_nonexistent_prompt():
    prompt = load_prompt("nonexistent.txt")
    assert prompt == ""


# Phase 1 tests - LLM Service
def test_llm_service_init():
    service = LLMService()
    assert service.base_url == "http://localhost:11434"


@pytest.mark.asyncio
async def test_llm_service_is_connected_success():
    service = LLMService()
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await service.is_connected()
        assert result is True


@pytest.mark.asyncio
async def test_llm_service_is_connected_failure():
    service = LLMService()
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection failed")):
        result = await service.is_connected()
        assert result is False


@pytest.mark.asyncio
async def test_llm_service_list_models_success():
    service = LLMService()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]}
    mock_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await service.list_models()
        assert result == ["qwen2.5:7b", "llama3:8b"]


@pytest.mark.asyncio
async def test_llm_service_list_models_failure():
    service = LLMService()
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection failed")):
        result = await service.list_models()
        assert result == []


# Phase 1 tests - API endpoints (mocked)
@pytest.mark.asyncio
async def test_chat_endpoint_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": "سلام! چطور می‌توانم کمک کنم؟"}}
    mock_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        response = client.post("/llm/chat", json={"message": "سلام"})
        assert response.status_code == 200
        assert "response" in response.json()


@pytest.mark.asyncio
async def test_chat_endpoint_connection_error():
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection failed")):
        response = client.post("/llm/chat", json={"message": "سلام"})
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_sql_test_endpoint_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {
            "content": '{"sql": "SELECT SUM(amount) FROM sales WHERE date >= \\"2024-01-01\\"", "confidence": "high", "explanation": "کوئری فروش ماه گذشته"}'
        }
    }
    mock_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        response = client.post("/llm/sql-test", json={"question": "فروش ماه گذشته چقدر بوده؟"})
        assert response.status_code == 200
        data = response.json()
        assert "sql" in data
        assert "confidence" in data
        assert "explanation" in data


@pytest.mark.asyncio
async def test_sql_test_endpoint_connection_error():
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection failed")):
        response = client.post("/llm/sql-test", json={"question": "فروش ماه گذشته چقدر بوده؟"})
        assert response.status_code == 503


def test_chat_endpoint_validation():
    response = client.post("/llm/chat", json={})
    assert response.status_code == 422


def test_sql_test_endpoint_validation():
    response = client.post("/llm/sql-test", json={})
    assert response.status_code == 422


# Phase 2 tests - Knowledge Loader (Nested Structure)
def test_knowledge_loader_init():
    loader = KnowledgeLoader(TENANT_DIR)
    assert loader.tenant_path == TENANT_DIR
    assert loader.business_path == BUSINESS_DIR
    assert loader.reports_path == REPORTS_DIR


def test_load_company():
    loader = KnowledgeLoader(TENANT_DIR)
    company = loader.load_company()
    assert company is not None
    assert company.name == "شرکت خرده فروشی نوین"
    assert company.industry == "خرده فروشی"


def test_load_definitions():
    loader = KnowledgeLoader(TENANT_DIR)
    definitions = loader.load_definitions()
    assert len(definitions) > 0
    assert any(d.term == "فروش خالص" for d in definitions)


def test_load_metrics():
    loader = KnowledgeLoader(TENANT_DIR)
    metrics = loader.load_metrics()
    assert len(metrics) > 0
    assert any(m.name == "فروش روزانه" for m in metrics)


def test_load_rules():
    loader = KnowledgeLoader(TENANT_DIR)
    rules = loader.load_rules()
    assert len(rules) > 0
    assert any(r.name == "قانون اعمال تخفیف" for r in rules)


def test_load_terminology():
    loader = KnowledgeLoader(TENANT_DIR)
    terminology = loader.load_terminology()
    assert len(terminology) > 0
    assert any(t.term == "فاکتور" for t in terminology)


def test_load_business():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    assert isinstance(context, CompanyContext)
    assert context.company is not None
    assert len(context.definitions) > 0
    assert len(context.metrics) > 0
    assert len(context.rules) > 0
    assert len(context.terminology) > 0


def test_load_missing_business_file():
    loader = KnowledgeLoader(Path("/nonexistent/path"))
    company = loader.load_company()
    assert company is None


def test_load_missing_definitions():
    loader = KnowledgeLoader(Path("/nonexistent/path"))
    definitions = loader.load_definitions()
    assert definitions == []


# Phase 2 tests - Report Loader
def test_load_report():
    loader = KnowledgeLoader(TENANT_DIR)
    report = loader.load_report("sales_report")
    assert report is not None
    assert report.id == "sales_report"
    assert report.name == "گزارش فروش"
    assert report.linked_table == "sales"


def test_load_all_reports():
    loader = KnowledgeLoader(TENANT_DIR)
    reports = loader.load_all_reports()
    assert len(reports) == 2
    report_ids = [r.id for r in reports]
    assert "sales_report" in report_ids
    assert "customer_report" in report_ids


def test_load_report_context():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    assert context is not None
    assert isinstance(context, ReportContext)
    assert context.report.id == "sales_report"
    assert len(context.metrics) > 0
    assert len(context.rules) > 0


def test_load_nonexistent_report():
    loader = KnowledgeLoader(TENANT_DIR)
    report = loader.load_report("nonexistent_report")
    assert report is None


def test_load_report_context_nonexistent():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("nonexistent_report")
    assert context is None


# Phase 2 tests - Context Builder
def test_context_builder_company():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    company_context = builder.build_company_context()
    assert "شرکت خرده فروشی نوین" in company_context
    assert "خرده فروشی" in company_context


def test_context_builder_definitions():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    definitions_context = builder.build_definitions_context()
    assert "تعریف‌های کسب‌وکار" in definitions_context
    assert "فروش خالص" in definitions_context


def test_context_builder_metrics():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    metrics_context = builder.build_metrics_context()
    assert "شاخص‌های کلیدی عملکرد" in metrics_context
    assert "فروش روزانه" in metrics_context


def test_context_builder_rules():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    rules_context = builder.build_rules_context()
    assert "قوانین کسب‌وکار" in rules_context
    assert "قانون اعمال تخفیف" in rules_context


def test_context_builder_terminology():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    terminology_context = builder.build_terminology_context()
    assert "اصطلاحات تخصصی" in terminology_context
    assert "فاکتور" in terminology_context


def test_context_builder_full():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    full_context = builder.build_full_context()
    assert "شرکت خرده فروشی نوین" in full_context
    assert "تعریف‌های کسب‌وکار" in full_context
    assert "شاخص‌های کلیدی عملکرد" in full_context
    assert "قوانین کسب‌وکار" in full_context
    assert "اصطلاحات تخصصی" in full_context


def test_context_builder_structured():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_business()
    builder = ContextBuilder(context)
    structured = builder.build_structured_context()
    assert "company_context" in structured
    assert "definitions" in structured
    assert "metrics" in structured
    assert "rules" in structured
    assert "terminology" in structured


# Phase 2 tests - Report Context Builder
def test_report_context_builder_info():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    info = builder.build_report_info()
    assert "گزارش فروش" in info
    assert "sales" in info


def test_report_context_builder_metrics():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    metrics = builder.build_metrics_context()
    assert "شاخص‌های مجاز" in metrics
    assert "فروش روزانه" in metrics


def test_report_context_builder_rules():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    rules = builder.build_rules_context()
    assert "قوانین مرتبط" in rules
    assert "قانون اعمال تخفیف" in rules


def test_report_context_builder_examples():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    examples = builder.build_examples_context()
    assert "نمونه سوالات" in examples
    assert "فروش ماه گذشته" in examples


def test_report_context_builder_full():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    full = builder.build_full_context()
    assert "گزارش فروش" in full
    assert "فروش روزانه" in full
    assert "قانون اعمال تخفیف" in full
    assert "نمونه سوالات" in full


def test_report_context_builder_structured():
    loader = KnowledgeLoader(TENANT_DIR)
    context = loader.load_report_context("sales_report")
    builder = ReportContextBuilder(context)
    structured = builder.build_structured_context()
    assert structured["report_name"] == "گزارش فروش"
    assert structured["table"] == "sales"
    assert "metrics" in structured
    assert "rules" in structured
    assert "examples" in structured


# Phase 2 tests - API endpoints
def test_knowledge_context_endpoint():
    response = client.get("/knowledge/context")
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert len(data["context"]) > 0


def test_knowledge_context_endpoint_structure():
    response = client.get("/knowledge/context")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["context"], str)
    assert len(data["context"]) > 0


def test_reports_list_endpoint():
    response = client.get("/knowledge/reports")
    assert response.status_code == 200
    data = response.json()
    assert "reports" in data
    assert len(data["reports"]) > 0
    report_ids = [r["id"] for r in data["reports"]]
    assert len(report_ids) == len(set(report_ids))


def test_report_context_endpoint():
    response = client.get("/knowledge/reports")
    assert response.status_code == 200
    first_report_id = response.json()["reports"][0]["id"]
    response = client.get(f"/knowledge/reports/{first_report_id}/context")
    assert response.status_code == 200
    data = response.json()
    assert "context" in data
    assert len(data["context"]) > 0


def test_report_context_endpoint_not_found():
    response = client.get("/knowledge/reports/nonexistent/context")
    assert response.status_code == 404


# Phase 2 tests - Tenant switching
def test_tenant_switching():
    loader1 = KnowledgeLoader(Path(__file__).parent.parent / "knowledge" / "tenants" / "retail_company")
    context1 = loader1.load_business()
    assert context1.company.name == "شرکت خرده فروشی نوین"
    
    loader2 = KnowledgeLoader(Path("/nonexistent/tenant"))
    context2 = loader2.load_business()
    assert context2.company is None
    assert len(context2.definitions) == 0


# Phase 3 tests - Report Intelligence
def test_embedding_config():
    settings = get_settings()
    assert "paraphrase-multilingual-mpnet-base-v2" in settings.embedding_model_path
    assert settings.embedding_device == "cpu"


def test_embedding_service_embed_text():
    from backend.reports.embedding import EmbeddingService
    service = EmbeddingService()
    embedding = service.embed_text("فروش ماه گذشته چقدر بوده؟")
    assert isinstance(embedding, list)
    assert len(embedding) > 0


def test_embedding_service_embed_batch():
    from backend.reports.embedding import EmbeddingService
    service = EmbeddingService()
    embeddings = service.embed_batch(["سوال اول", "سوال دوم"])
    assert isinstance(embeddings, list)
    assert len(embeddings) == 2
    assert len(embeddings[0]) > 0


def test_embedding_service_dimension():
    from backend.reports.embedding import EmbeddingService
    service = EmbeddingService()
    dim = service.get_dimension()
    assert dim == 768


def test_embedding_service_model_loaded():
    from backend.reports.embedding import EmbeddingService
    service = EmbeddingService()
    model = service._load_model()
    assert model is not None
    assert hasattr(model, 'encode')


def test_embedding_service_model_config():
    from backend.config import get_settings
    settings = get_settings()
    assert "paraphrase-multilingual-mpnet-base-v2" in settings.embedding_model_path


def test_vector_store_collection():
    from backend.reports.vector_store import VectorStore
    store = VectorStore()
    collection = store.get_collection("test_tenant")
    assert collection is not None
    assert collection.name == "reports_test_tenant"


def test_vector_store_add_and_query():
    from backend.reports.vector_store import VectorStore
    from backend.reports.embedding import EmbeddingService
    
    store = VectorStore()
    embedding_service = EmbeddingService()
    
    test_id = "test_report_1"
    test_doc = "گزارش فروش ماهانه"
    test_metadata = {"report_id": "sales_report", "tenant_id": "test_tenant", "linked_table": "sales"}
    test_embedding = embedding_service.embed_text(test_doc)
    
    store.add_documents(
        tenant_id="test_tenant",
        ids=[test_id],
        documents=[test_doc],
        metadatas=[test_metadata],
        embeddings=[test_embedding]
    )
    
    query_embedding = embedding_service.embed_text("فروش")
    results = store.query(tenant_id="test_tenant", query_embedding=query_embedding, n_results=1)
    assert results["ids"] is not None
    assert len(results["ids"]) > 0


def test_vector_store_delete_collection():
    from backend.reports.vector_store import VectorStore
    
    store = VectorStore()
    store.get_collection("delete_test")
    store.delete_collection("delete_test")
    
    count = store.get_collection_count("delete_test")
    assert count == 0


def test_report_retriever_sync():
    from backend.reports.retriever import ReportRetriever
    
    retriever = ReportRetriever()
    count = retriever.sync_reports("retail_company")
    assert count == 2


def test_report_retriever_search_sales():
    from backend.reports.retriever import ReportRetriever
    
    retriever = ReportRetriever()
    retriever.sync_reports("retail_company")
    
    result = retriever.search_reports("retail_company", "فروش ماه قبل چقدر بوده؟")
    assert result["report_id"] in ["sales_report", "customer_report"]


def test_report_retriever_search_customer():
    from backend.reports.retriever import ReportRetriever
    
    retriever = ReportRetriever()
    retriever.sync_reports("retail_company")
    
    result = retriever.search_reports("retail_company", "تعداد مشتریان فعال؟")
    assert result["report_id"] in ["sales_report", "customer_report"]


def test_report_retriever_search_no_results():
    from backend.reports.retriever import ReportRetriever
    
    retriever = ReportRetriever()
    result = retriever.search_reports("nonexistent_tenant", "test")
    assert result["report_id"] == ""
    assert result["confidence"] == 0.0


def test_report_service_sync():
    from backend.reports.service import ReportService
    
    service = ReportService()
    result = service.sync_reports("retail_company")
    assert result.status == "success"
    assert result.reports_synced == 2


def test_report_service_search():
    from backend.reports.service import ReportService
    
    service = ReportService()
    service.sync_reports("retail_company")
    
    result = service.search_reports("retail_company", "فروش ماه قبل چقدر بوده؟")
    assert result.report_id in ["sales_report", "customer_report"]


def test_tenant_isolation():
    from backend.reports.vector_store import VectorStore
    from backend.reports.embedding import EmbeddingService
    
    store = VectorStore()
    embedding_service = EmbeddingService()
    
    embedding = embedding_service.embed_text("test")
    
    store.add_documents(
        tenant_id="tenant_iso_a",
        ids=["doc_a"],
        documents=["document for tenant A"],
        metadatas=[{"report_id": "report_a"}],
        embeddings=[embedding]
    )
    
    store.add_documents(
        tenant_id="tenant_iso_b",
        ids=["doc_b"],
        documents=["document for tenant B"],
        metadatas=[{"report_id": "report_b"}],
        embeddings=[embedding]
    )
    
    results_a = store.query(tenant_id="tenant_iso_a", query_embedding=embedding, n_results=1)
    results_b = store.query(tenant_id="tenant_iso_b", query_embedding=embedding, n_results=1)
    
    assert results_a["metadatas"][0][0]["report_id"] == "report_a"
    assert results_b["metadatas"][0][0]["report_id"] == "report_b"


# Phase 3 tests - API endpoints
def test_sync_reports_endpoint():
    response = client.post("/reports/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["reports_synced"] > 0


def test_search_reports_endpoint():
    client.post("/reports/groups/sync")
    client.post("/reports/sync")
    
    response = client.post("/reports/search", json={"question": "فروش ماه قبل چقدر بوده؟"})
    assert response.status_code == 200
    data = response.json()
    assert "group_id" in data
    assert "report_id" in data


def test_search_reports_customer():
    client.post("/reports/groups/sync")
    client.post("/reports/sync")
    
    response = client.post("/reports/search", json={"question": "تعداد مشتریان فعال؟"})
    assert response.status_code == 200
    data = response.json()
    assert "group_id" in data
    assert "report_id" in data


# Phase 4 tests - Database Schema Discovery
def test_database_models():
    from backend.database.models import (
        ColumnInfo, TableInfo, ForeignKeyInfo, RelationshipInfo,
        DatabaseSchema, SchemaSyncResponse
    )
    
    col = ColumnInfo(name="id", data_type="integer", is_primary_key=True)
    assert col.name == "id"
    assert col.is_primary_key is True
    
    table = TableInfo(name="employees", columns=[col], primary_keys=["id"])
    assert table.name == "employees"
    assert len(table.columns) == 1
    
    fk = ForeignKeyInfo(
        table_name="salary_items",
        column_name="employee_id",
        foreign_table_name="employees",
        foreign_column_name="id"
    )
    assert fk.table_name == "salary_items"
    
    rel = RelationshipInfo(
        source_table="salary_items",
        source_column="employee_id",
        target_table="employees",
        target_column="id"
    )
    assert rel.source_table == "salary_items"
    
    schema = DatabaseSchema(tables=[table], foreign_keys=[fk], relationships=[rel])
    assert len(schema.tables) == 1
    assert len(schema.foreign_keys) == 1


def test_relationship_graph_build():
    from backend.database.relationship_graph import RelationshipGraph
    from backend.database.models import ForeignKeyInfo
    
    graph = RelationshipGraph()
    foreign_keys = [
        ForeignKeyInfo(table_name="salary_items", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
        ForeignKeyInfo(table_name="employees", column_name="organization_unit_id", foreign_table_name="organization_units", foreign_column_name="id"),
        ForeignKeyInfo(table_name="ranking_requests", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
        ForeignKeyInfo(table_name="retirement_records", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
        ForeignKeyInfo(table_name="schools", column_name="organization_unit_id", foreign_table_name="organization_units", foreign_column_name="id"),
        ForeignKeyInfo(table_name="students", column_name="school_id", foreign_table_name="schools", foreign_column_name="id"),
    ]
    
    relationships = graph.build_from_foreign_keys(foreign_keys)
    assert len(relationships) == 6


def test_relationship_graph_find_path():
    from backend.database.relationship_graph import RelationshipGraph
    from backend.database.models import ForeignKeyInfo
    
    graph = RelationshipGraph()
    foreign_keys = [
        ForeignKeyInfo(table_name="salary_items", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
        ForeignKeyInfo(table_name="employees", column_name="organization_unit_id", foreign_table_name="organization_units", foreign_column_name="id"),
    ]
    
    graph.build_from_foreign_keys(foreign_keys)
    
    path = graph.find_join_path("salary_items", "employees")
    assert len(path) == 1
    assert path[0]["from_table"] == "salary_items"
    assert path[0]["to_table"] == "employees"


def test_relationship_graph_get_for_table():
    from backend.database.relationship_graph import RelationshipGraph
    from backend.database.models import ForeignKeyInfo
    
    graph = RelationshipGraph()
    foreign_keys = [
        ForeignKeyInfo(table_name="salary_items", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
        ForeignKeyInfo(table_name="employees", column_name="organization_unit_id", foreign_table_name="organization_units", foreign_column_name="id"),
        ForeignKeyInfo(table_name="ranking_requests", column_name="employee_id", foreign_table_name="employees", foreign_column_name="id"),
    ]
    
    graph.build_from_foreign_keys(foreign_keys)
    
    emp_rels = graph.get_relationships_for_table("employees")
    assert len(emp_rels) == 3


def test_schema_sync_service_init():
    from backend.database.sync_service import SchemaSyncService
    service = SchemaSyncService()
    assert service.schema_dir.exists()


def test_schema_sync_service_get_tenant_dir():
    from backend.database.sync_service import SchemaSyncService
    service = SchemaSyncService()
    tenant_dir = service._get_tenant_schema_dir("test_tenant")
    assert tenant_dir.exists()
    assert tenant_dir.name == "test_tenant"


def test_schema_loader_get_tables():
    from unittest.mock import MagicMock, patch
    from backend.database.schema_loader import SchemaLoader
    
    loader = SchemaLoader()
    
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([
        ("employees",),
        ("organization_units",),
        ("salary_items",),
    ]))
    
    with patch.object(loader.connection, 'execute_query', return_value=mock_result):
        tables = loader.get_tables()
        assert len(tables) == 3
        assert "employees" in tables


def test_schema_loader_get_foreign_keys():
    from unittest.mock import MagicMock, patch
    from backend.database.schema_loader import SchemaLoader
    
    loader = SchemaLoader()
    
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([
        ("salary_items", "employee_id", "employees", "id"),
        ("employees", "organization_unit_id", "organization_units", "id"),
    ]))
    
    with patch.object(loader.connection, 'execute_query', return_value=mock_result):
        fks = loader.get_foreign_keys()
        assert len(fks) == 2
        assert fks[0].table_name == "salary_items"


def test_api_database_sync_endpoint():
    from unittest.mock import MagicMock, patch
    from backend.database.models import SchemaSyncResponse
    
    mock_response = SchemaSyncResponse(
        tenant_id="education_ministry",
        tables_discovered=7,
        relationships_found=6,
        status="success"
    )
    
    with patch("backend.api.main.schema_sync_service") as mock_service:
        mock_service.sync_schema.return_value = mock_response
        response = client.post("/database/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["tables_discovered"] == 7


def test_api_database_schema_endpoint():
    from unittest.mock import MagicMock, patch
    from backend.database.models import DatabaseSchema, TableInfo, ColumnInfo
    
    mock_schema = DatabaseSchema(
        tables=[
            TableInfo(
                name="employees",
                columns=[ColumnInfo(name="id", data_type="integer", is_primary_key=True)],
                primary_keys=["id"],
                row_count=8
            )
        ],
        foreign_keys=[],
        relationships=[]
    )
    
    with patch("backend.api.main.schema_sync_service") as mock_service:
        mock_service.load_schema.return_value = mock_schema
        response = client.get("/database/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["total_tables"] == 1
        assert data["tables"][0]["name"] == "employees"


def test_api_database_relationships_endpoint():
    from unittest.mock import MagicMock, patch
    from backend.database.models import DatabaseSchema, RelationshipInfo
    
    mock_schema = DatabaseSchema(
        tables=[],
        foreign_keys=[],
        relationships=[
            RelationshipInfo(
                source_table="salary_items",
                source_column="employee_id",
                target_table="employees",
                target_column="id"
            )
        ]
    )
    
    with patch("backend.api.main.schema_sync_service") as mock_service:
        mock_service.load_schema.return_value = mock_schema
        response = client.get("/database/relationships")
        assert response.status_code == 200
        data = response.json()
        assert data["total_relationships"] == 1
        assert data["relationships"][0]["source_table"] == "salary_items"


# Phase 4.5 tests - Group Intelligence
def test_group_models():
    from backend.reports.group_models import (
        ReportGroup, ReportGroupSearchResult, TwoStageSearchResult,
        ReportGroupSyncResponse, ReportGroupSearchRequest
    )
    
    group = ReportGroup(
        id="salary",
        name="گروه حقوق",
        description="گزارش‌های حقوقی",
        linked_tables=["salary_items"],
        example_questions=["حقوق ماه گذشته"]
    )
    assert group.id == "salary"
    assert len(group.linked_tables) == 1
    
    result = ReportGroupSearchResult(
        group_id="salary",
        group_name="گروه حقوق",
        confidence=0.85,
        reason="یافت شد"
    )
    assert result.group_id == "salary"
    
    two_stage = TwoStageSearchResult(
        group_id="salary",
        group_name="گروه حقوق",
        report_id="salary_summary",
        report_name="خلاصه حقوق",
        confidence=0.8,
        reason="گروه و گزارش یافت شد"
    )
    assert two_stage.report_id == "salary_summary"


def test_group_loader():
    from backend.reports.group_loader import GroupLoader
    
    loader = GroupLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    groups = loader.load_all_groups()
    assert len(groups) == 5
    
    group_ids = [g.id for g in groups]
    assert "salary" in group_ids
    assert "employee" in group_ids
    assert "organization" in group_ids
    assert "ranking" in group_ids
    assert "student" in group_ids


def test_group_loader_single():
    from backend.reports.group_loader import GroupLoader
    
    loader = GroupLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    group = loader.load_group("salary")
    assert group is not None
    assert group.id == "salary"
    assert group.name == "گروه حقوق و مزایا"
    assert "salary_items" in group.linked_tables


def test_group_retriever_sync():
    from backend.reports.group_retriever import GroupRetriever
    
    retriever = GroupRetriever()
    count = retriever.sync_groups("education_ministry")
    assert count == 5


def test_group_retriever_search():
    from backend.reports.group_retriever import GroupRetriever
    
    retriever = GroupRetriever()
    retriever.sync_groups("education_ministry")
    
    result = retriever.search_groups("education_ministry", "حقوق ماه گذشته")
    assert result["group_id"] in ["salary", "employee", "organization", "ranking", "student"]


def test_intelligence_service_sync_groups():
    from backend.reports.intelligence_service import IntelligenceService
    
    service = IntelligenceService()
    result = service.sync_groups("education_ministry")
    assert result.status == "success"
    assert result.groups_synced == 5


def test_intelligence_service_sync_reports():
    from backend.reports.intelligence_service import IntelligenceService
    
    service = IntelligenceService()
    result = service.sync_reports("education_ministry")
    assert result.status == "success"
    assert result.reports_synced > 0


def test_report_has_group_id():
    from backend.knowledge.loader import KnowledgeLoader
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    for report in reports:
        assert report.group_id is not None


def test_report_with_group_id_search():
    from backend.reports.retriever import ReportRetriever
    
    retriever = ReportRetriever()
    retriever.sync_reports("education_ministry")
    
    result = retriever.search_reports(
        "education_ministry",
        "حقوق ماه گذشته",
        group_filter="salary"
    )
    assert result["report_id"] != ""


def test_two_stage_search():
    from backend.reports.intelligence_service import IntelligenceService
    
    service = IntelligenceService()
    service.sync_groups("education_ministry")
    service.sync_reports("education_ministry")
    
    result = service.search_two_stage("education_ministry", "حقوق ماه گذشته")
    assert result.group_id != ""
    assert result.report_id != ""


def test_api_sync_groups_endpoint():
    from unittest.mock import patch
    from backend.reports.group_models import ReportGroupSyncResponse
    
    mock_response = ReportGroupSyncResponse(
        tenant_id="education_ministry",
        groups_synced=5,
        status="success"
    )
    
    with patch("backend.api.main.intelligence_service") as mock_service:
        mock_service.sync_groups.return_value = mock_response
        response = client.post("/reports/groups/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["groups_synced"] == 5


def test_api_search_groups_endpoint():
    from unittest.mock import patch
    
    with patch("backend.reports.group_retriever.GroupRetriever.search_groups") as mock_search:
        mock_search.return_value = {
            "group_id": "salary",
            "group_name": "گروه حقوق",
            "confidence": 0.85,
            "reason": "یافت شد"
        }
        response = client.post("/reports/groups/search", json={"question": "حقوق ماه گذشته"})
        assert response.status_code == 200
        data = response.json()
        assert data["group_id"] == "salary"


def test_api_search_two_stage_endpoint():
    from unittest.mock import patch
    from backend.reports.group_models import TwoStageSearchResult
    
    mock_result = TwoStageSearchResult(
        group_id="salary",
        group_name="گروه حقوق",
        report_id="salary_summary",
        report_name="خلاصه حقوق",
        confidence=0.8,
        reason="گروه و گزارش یافت شد"
    )
    
    with patch("backend.api.main.intelligence_service") as mock_service:
        mock_service.search_two_stage.return_value = mock_result
        response = client.post("/reports/search", json={"question": "حقوق ماه گذشته"})
        assert response.status_code == 200
        data = response.json()
        assert data["group_id"] == "salary"
        assert data["report_id"] == "salary_summary"


# Phase 5 tests - SQL Planning + Generation + Validation
def test_sql_models():
    from backend.sql.models import SQLPlan, GeneratedSQL, ValidationResult, SQLRequest, SQLResponse
    
    plan = SQLPlan(
        required_tables=["students"],
        selected_columns=["*"]
    )
    assert plan.required_tables == ["students"]
    
    generated = GeneratedSQL(
        sql="SELECT * FROM students",
        explanation="لیست دانش‌آموزان",
        confidence=0.9
    )
    assert generated.sql == "SELECT * FROM students"
    
    validation = ValidationResult(is_valid=True)
    assert validation.is_valid is True


def test_sql_planner_detect_tables():
    from backend.sql.planner import SQLPlanner
    from backend.database.models import DatabaseSchema, TableInfo, ColumnInfo
    
    planner = SQLPlanner()
    
    schema = DatabaseSchema(
        tables=[
            TableInfo(name="students", columns=[ColumnInfo(name="id", data_type="integer")]),
            TableInfo(name="employees", columns=[ColumnInfo(name="id", data_type="integer")]),
        ]
    )
    
    tables = planner.detect_tables("لیست دانش آموزان", schema)
    assert "students" in tables


def test_sql_planner_detect_aggregations():
    from backend.sql.planner import SQLPlanner
    
    planner = SQLPlanner()
    
    aggs = planner.detect_aggregations("تعداد دانش آموزان")
    assert len(aggs) > 0
    assert aggs[0]["function"] == "COUNT"


def test_sql_planner_create_plan():
    from backend.sql.planner import SQLPlanner
    from backend.database.models import DatabaseSchema, TableInfo, ColumnInfo, RelationshipInfo
    
    planner = SQLPlanner()
    
    schema = DatabaseSchema(
        tables=[
            TableInfo(name="students", columns=[ColumnInfo(name="id", data_type="integer"), ColumnInfo(name="school_id", data_type="integer")]),
            TableInfo(name="schools", columns=[ColumnInfo(name="id", data_type="integer"), ColumnInfo(name="name", data_type="varchar")]),
        ],
        relationships=[
            RelationshipInfo(source_table="students", source_column="school_id", target_table="schools", target_column="id")
        ]
    )
    
    plan = planner.create_plan("لیست دانش آموزان هر مدرسه", schema)
    assert "students" in plan.required_tables
    assert "schools" in plan.required_tables
    assert len(plan.joins) > 0


def test_sql_validator_select_only():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema, TableInfo
    
    validator = SQLValidator()
    schema = DatabaseSchema(
        tables=[TableInfo(name="students", columns=[])]
    )
    
    result = validator.validate("SELECT * FROM students", schema)
    assert result.is_valid is True


def test_sql_validator_reject_drop():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema
    
    validator = SQLValidator()
    schema = DatabaseSchema(tables=[])
    
    result = validator.validate("DROP TABLE students", schema)
    assert result.is_valid is False
    assert any("ممنوعه" in e for e in result.errors)


def test_sql_validator_reject_delete():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema
    
    validator = SQLValidator()
    schema = DatabaseSchema(tables=[])
    
    result = validator.validate("DELETE FROM students", schema)
    assert result.is_valid is False


def test_sql_validator_reject_update():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema
    
    validator = SQLValidator()
    schema = DatabaseSchema(tables=[])
    
    result = validator.validate("UPDATE students SET name='test'", schema)
    assert result.is_valid is False


def test_sql_validator_reject_insert():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema
    
    validator = SQLValidator()
    schema = DatabaseSchema(tables=[])
    
    result = validator.validate("INSERT INTO students VALUES (1)", schema)
    assert result.is_valid is False


def test_sql_validator_unknown_table():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema, TableInfo
    
    validator = SQLValidator()
    schema = DatabaseSchema(
        tables=[TableInfo(name="students", columns=[])]
    )
    
    result = validator.validate("SELECT * FROM nonexistent_table", schema)
    assert result.is_valid is False
    assert any("یافت نشد" in e for e in result.errors)


def test_sql_validator_syntax_error():
    from backend.sql.validator import SQLValidator
    from backend.database.models import DatabaseSchema
    
    validator = SQLValidator()
    schema = DatabaseSchema(tables=[])
    
    result = validator.validate("SELECT * FROM students (", schema)
    assert result.is_valid is False
    assert any("پرانتز" in e for e in result.errors)


def test_sql_service_plan_only():
    from backend.sql.service import SQLService
    from backend.database.models import DatabaseSchema, TableInfo, ColumnInfo
    
    service = SQLService()
    
    mock_schema = DatabaseSchema(
        tables=[TableInfo(name="students", columns=[ColumnInfo(name="id", data_type="integer")])]
    )
    
    with patch("backend.sql.service.schema_sync_service") as mock_sync:
        mock_sync.load_schema.return_value = mock_schema
        plan = service.plan_only("لیست دانش آموزان", "education_ministry")
        assert plan is not None
        assert len(plan.required_tables) > 0


def test_sql_service_validate_only():
    from backend.sql.service import SQLService
    from backend.database.models import DatabaseSchema, TableInfo
    
    service = SQLService()
    
    mock_schema = DatabaseSchema(
        tables=[TableInfo(name="students", columns=[])]
    )
    
    with patch("backend.sql.service.schema_sync_service") as mock_sync:
        mock_sync.load_schema.return_value = mock_schema
        result = service.validate_only("SELECT * FROM students", "education_ministry")
        assert result.is_valid is True


def test_sql_service_validate_dangerous():
    from backend.sql.service import SQLService
    
    service = SQLService()
    
    result = service.validate_only("DROP TABLE students", "education_ministry")
    assert result.is_valid is False


def test_api_sql_generate_endpoint():
    from unittest.mock import patch, AsyncMock
    from backend.sql.models import SQLResponse, SQLPlan, ValidationResult
    
    mock_response = SQLResponse(
        plan=SQLPlan(required_tables=["students"]),
        sql="SELECT * FROM students",
        valid=True,
        validation=ValidationResult(is_valid=True),
        explanation="لیست دانش آموزان",
        confidence=0.9
    )
    
    with patch("backend.api.main.sql_service") as mock_service:
        mock_service.generate_sql = AsyncMock(return_value=mock_response)
        response = client.post("/sql/generate", json={"question": "لیست دانش آموزان"})
        assert response.status_code == 200
        data = response.json()
        assert data["sql"] == "SELECT * FROM students"
        assert data["valid"] is True


# Knowledge Refactoring Tests
def test_report_column_definition():
    from backend.knowledge.models import ReportColumnDefinition
    
    col = ReportColumnDefinition(
        meaning="شناسه کارمند",
        persian_name="کد کارمند",
        data_type="integer"
    )
    assert col.meaning == "شناسه کارمند"
    assert col.persian_name == "کد کارمند"


def test_sql_hint():
    from backend.knowledge.models import SQLHint
    
    hint = SQLHint(
        default_filters=["status = 'active'"],
        preferred_joins=["salary_items.employee_id = employees.id"],
        aggregate_columns=["net_salary"],
        group_by_columns=["month"]
    )
    assert len(hint.default_filters) == 1
    assert len(hint.preferred_joins) == 1


def test_report_with_sql_hints():
    from backend.knowledge.loader import KnowledgeLoader
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    salary_report = next((r for r in reports if r.id == "salary_summary"), None)
    assert salary_report is not None
    assert salary_report.sql_hints is not None
    assert len(salary_report.sql_hints.preferred_joins) > 0
    assert len(salary_report.important_columns) > 0


def test_report_important_columns():
    from backend.knowledge.loader import KnowledgeLoader
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    for report in reports:
        assert len(report.important_columns) > 0


def test_context_builder_columns():
    from backend.knowledge.loader import KnowledgeLoader
    from backend.knowledge.context_builder import ReportContextBuilder
    from backend.knowledge.models import ReportContext
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    salary_report = next((r for r in reports if r.id == "salary_summary"), None)
    assert salary_report is not None
    
    context = ReportContext(report=salary_report)
    builder = ReportContextBuilder(context)
    
    columns_context = builder.build_columns_context()
    assert "ستون‌های مهم" in columns_context
    assert "employee_id" in columns_context


def test_context_builder_sql_hints():
    from backend.knowledge.loader import KnowledgeLoader
    from backend.knowledge.context_builder import ReportContextBuilder
    from backend.knowledge.models import ReportContext
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    salary_report = next((r for r in reports if r.id == "salary_summary"), None)
    assert salary_report is not None
    
    context = ReportContext(report=salary_report)
    builder = ReportContextBuilder(context)
    
    hints_context = builder.build_sql_hints_context()
    assert "نکات SQL" in hints_context
    assert "اتصالات ترجیحی" in hints_context


def test_context_builder_full_with_hints():
    from backend.knowledge.loader import KnowledgeLoader
    from backend.knowledge.context_builder import ReportContextBuilder
    from backend.knowledge.models import ReportContext
    
    loader = KnowledgeLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    reports = loader.load_all_reports()
    
    salary_report = next((r for r in reports if r.id == "salary_summary"), None)
    assert salary_report is not None
    
    context = ReportContext(report=salary_report)
    builder = ReportContextBuilder(context)
    
    full_context = builder.build_full_context()
    assert "ستون‌های مهم" in full_context
    assert "نکات SQL" in full_context
    assert "اتصالات ترجیحی" in full_context


def test_prompt_builder_with_report():
    from backend.sql.prompt_builder import PromptBuilder
    from backend.sql.models import SQLPlan
    from backend.database.models import DatabaseSchema, TableInfo, ColumnInfo
    from backend.knowledge.models import Report, ReportColumnDefinition, SQLHint
    
    builder = PromptBuilder()
    
    plan = SQLPlan(
        required_tables=["salary_items"],
        selected_columns=["*"]
    )
    
    schema = DatabaseSchema(
        tables=[
            TableInfo(
                name="salary_items",
                columns=[
                    ColumnInfo(name="id", data_type="integer", is_primary_key=True),
                    ColumnInfo(name="employee_id", data_type="integer"),
                    ColumnInfo(name="net_salary", data_type="decimal"),
                ]
            )
        ]
    )
    
    report = Report(
        id="salary_summary",
        name="خلاصه حقوق",
        description="گزارش حقوق",
        linked_table="salary_items",
        important_columns={
            "net_salary": ReportColumnDefinition(meaning="خالص پرداختی")
        },
        sql_hints=SQLHint(
            preferred_joins=["salary_items.employee_id = employees.id"]
        )
    )
    
    prompt = builder.build_full_prompt(
        question="حقوق ماه گذشته",
        plan=plan,
        schema=schema,
        report=report
    )
    
    assert "salary_items" in prompt
    assert "net_salary" in prompt
    assert "اتصالات ترجیحی" in prompt


def test_sql_service_find_report():
    from backend.sql.service import SQLService
    
    service = SQLService()
    
    report = service._find_report_by_table("education_ministry", "salary_items")
    assert report is not None
    assert report.linked_table == "salary_items"


def test_rules_directory_exists():
    rules_path = PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry" / "rules"
    assert rules_path.exists()
    
    business_rules_file = rules_path / "business_rules.yaml"
    assert business_rules_file.exists()


# Phase 5.9.2 tests - Entity Priority Scoring
def test_entity_term_model():
    from backend.reports.group_models import EntityTerm
    
    entity = EntityTerm(term="دانش‌آموز", weight=3.0)
    assert entity.term == "دانش‌آموز"
    assert entity.weight == 3.0


def test_group_entity_terms():
    from backend.reports.group_loader import GroupLoader
    
    loader = GroupLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    groups = loader.load_all_groups()
    
    student_group = next((g for g in groups if g.id == "student"), None)
    assert student_group is not None
    assert len(student_group.entity_terms) > 0
    
    entity_terms = {e.term for e in student_group.entity_terms}
    assert "دانش‌آموز" in entity_terms or "دانش آموز" in entity_terms


def test_entity_boost():
    from backend.reports.group_retriever import GroupRetriever
    from backend.reports.group_loader import GroupLoader
    
    retriever = GroupRetriever()
    loader = GroupLoader(PROJECT_ROOT / "knowledge" / "tenants" / "education_ministry")
    groups = loader.load_all_groups()
    
    student_group = next((g for g in groups if g.id == "student"), None)
    
    boost1 = retriever._entity_boost("دانش‌آموزان فعال", student_group)
    boost2 = retriever._entity_boost("سلام دنیا", student_group)
    
    assert boost1 > boost2


def test_employee_question_maps_to_employee():
    from backend.reports.group_retriever import group_retriever
    
    group_retriever.sync_groups("education_ministry")
    result = group_retriever.search_groups("education_ministry", "لیست مدیران مدارس")
    assert result["group_id"] == "employee"


def test_student_question_maps_to_student():
    from backend.reports.group_retriever import group_retriever
    
    group_retriever.sync_groups("education_ministry")
    result = group_retriever.search_groups("education_ministry", "دانش‌آموزان فعال استان تهران")
    assert result["group_id"] == "student"


def test_organization_question_maps_to_organization():
    from backend.reports.group_retriever import group_retriever
    
    group_retriever.sync_groups("education_ministry")
    result = group_retriever.search_groups("education_ministry", "تعداد کارکنان هر واحد سازمانی")
    assert result["group_id"] == "organization"


# Phase 5.6 tests - Benchmark
def test_benchmark_dataset():
    from tests.benchmark.dataset import create_education_dataset
    
    dataset = create_education_dataset()
    assert dataset.get_count() == 20
    assert len(dataset.get_categories()) == 4


def test_benchmark_dataset_categories():
    from tests.benchmark.dataset import create_education_dataset
    
    dataset = create_education_dataset()
    counts = dataset.get_count_by_category()
    assert counts.get("salary") == 5
    assert counts.get("employee") == 5
    assert counts.get("student") == 5
    assert counts.get("organization") == 5


def test_benchmark_evaluator():
    from tests.benchmark.dataset import create_education_dataset, BenchmarkCase
    from tests.benchmark.evaluator import BenchmarkEvaluator
    
    dataset = create_education_dataset()
    evaluator = BenchmarkEvaluator("retail_company")
    
    case = dataset.get_cases()[0]
    result = evaluator.evaluate_case(case)
    
    assert result.case.id == case.id
    assert result.total_time > 0


def test_benchmark_report():
    from tests.benchmark.dataset import create_education_dataset
    from tests.benchmark.evaluator import BenchmarkEvaluator, BenchmarkReport
    
    dataset = create_education_dataset()
    evaluator = BenchmarkEvaluator("retail_company")
    results = evaluator.evaluate_dataset(dataset)
    
    report = BenchmarkReport(results)
    summary = report.get_summary()
    
    assert summary["total_cases"] == 20
    assert "group_accuracy" in summary
    assert "report_accuracy" in summary
    assert "tables_accuracy" in summary


def test_benchmark_by_category():
    from tests.benchmark.dataset import create_education_dataset
    from tests.benchmark.evaluator import BenchmarkEvaluator, BenchmarkReport
    
    dataset = create_education_dataset()
    evaluator = BenchmarkEvaluator("retail_company")
    results = evaluator.evaluate_dataset(dataset)
    
    report = BenchmarkReport(results)
    by_category = report.get_by_category()
    
    assert "salary" in by_category
    assert "employee" in by_category
    assert "student" in by_category
    assert "organization" in by_category


def test_benchmark_failed_cases():
    from tests.benchmark.dataset import create_education_dataset
    from tests.benchmark.evaluator import BenchmarkEvaluator, BenchmarkReport
    
    dataset = create_education_dataset()
    evaluator = BenchmarkEvaluator("retail_company")
    results = evaluator.evaluate_dataset(dataset)
    
    report = BenchmarkReport(results)
    failed = report.get_failed_cases()
    
    assert isinstance(failed, list)


def test_group_retrieval_output_format():
    from backend.reports.group_retriever import group_retriever
    
    result = group_retriever.search_groups("retail_company", "test question")
    
    assert "group_id" in result
    assert "group_name" in result
    assert "confidence" in result
    assert "reason" in result
    assert isinstance(result["group_id"], str)
    assert isinstance(result["group_name"], str)
    assert isinstance(result["confidence"], float)


def test_group_retrieval_format_matches_benchmark():
    from backend.reports.group_retriever import group_retriever
    
    group_result = group_retriever.search_groups("retail_company", "test")
    
    expected_keys = {"group_id", "group_name", "confidence", "reason"}
    assert expected_keys.issubset(set(group_result.keys()))
    
    assert isinstance(group_result["group_id"], str)
    assert isinstance(group_result["group_name"], str)
    assert isinstance(group_result["confidence"], (int, float))


# Phase 7.1 tests - Grounding, Structured Output, and Ambiguity Fix
def test_structured_sql_rejects_malformed_json():
    from backend.sql.structured import parse_structured_sql_response

    with pytest.raises(ValueError):
        parse_structured_sql_response("SELECT * FROM students")


def test_structured_sql_accepts_fenced_json():
    from backend.sql.structured import parse_structured_sql_response

    parsed = parse_structured_sql_response(
        '```json\n{"sql":"SELECT COUNT(students.id) FROM students","explanation":"ok","confidence":0.9}\n```'
    )
    assert parsed.sql == "SELECT COUNT(students.id) FROM students"


def test_structured_sql_rejects_fenced_sql():
    from backend.sql.structured import parse_structured_sql_response

    with pytest.raises(ValueError):
        parse_structured_sql_response("```sql\nSELECT * FROM students\n```")


def test_structured_sql_rejects_multiple_statements():
    from backend.sql.structured import parse_structured_sql_response

    with pytest.raises(ValueError):
        parse_structured_sql_response(
            '{"sql":"SELECT * FROM students; DROP TABLE students","explanation":"bad","confidence":0.1}'
        )


def test_sql_validator_rejects_unknown_column_strict():
    from backend.database.sync_service import schema_sync_service
    from backend.sql.validator import SQLValidator

    schema = schema_sync_service.load_schema("education_ministry")
    validator = SQLValidator()
    result = validator.validate(
        "SELECT salary_items.unknown_salary FROM salary_items",
        schema,
    )
    assert result.is_valid is False
    assert any("ستون ناشناخته" in error for error in result.errors)


def test_sql_validator_rejects_unknown_table_strict():
    from backend.database.sync_service import schema_sync_service
    from backend.sql.validator import SQLValidator

    schema = schema_sync_service.load_schema("education_ministry")
    validator = SQLValidator()
    result = validator.validate("SELECT mystery.id FROM mystery", schema)
    assert result.is_valid is False
    assert any("جدول" in error for error in result.errors)


def test_sql_validator_rejects_missing_where_constraint():
    from backend.database.sync_service import schema_sync_service
    from backend.pipeline.intent import extract_intent
    from backend.sql.validator import SQLValidator

    schema = schema_sync_service.load_schema("education_ministry")
    intent = extract_intent("درخواست های رتبه بندی تایید نشده را نمایش بده")
    result = SQLValidator().validate(
        "SELECT ranking_requests.id FROM ranking_requests",
        schema,
        intent=intent,
    )
    assert result.is_valid is False
    assert any("فیلتر ضروری" in error for error in result.errors)


def test_sql_validator_rejects_missing_order_by_and_limit():
    from backend.database.sync_service import schema_sync_service
    from backend.pipeline.intent import extract_intent
    from backend.sql.validator import SQLValidator

    schema = schema_sync_service.load_schema("education_ministry")
    intent = extract_intent("بیشترین حقوق پرداختی مربوط به چه کسی است؟")
    result = SQLValidator().validate(
        "SELECT employees.first_name, SUM(salary_items.net_salary) AS total_salary "
        "FROM salary_items JOIN employees ON salary_items.employee_id = employees.id "
        "GROUP BY employees.first_name",
        schema,
        intent=intent,
    )
    assert result.is_valid is False
    assert any("مرتب" in error or "LIMIT" in error for error in result.errors)


def test_invalid_status_mapping_is_rejected():
    from backend.database.sync_service import schema_sync_service
    from backend.pipeline.intent import extract_intent
    from backend.sql.validator import SQLValidator

    schema = schema_sync_service.load_schema("education_ministry")
    intent = extract_intent("درخواست های رتبه بندی تایید نشده را نمایش بده")
    result = SQLValidator().validate(
        "SELECT ranking_requests.id FROM ranking_requests WHERE ranking_requests.status = 'unapproved'",
        schema,
        intent=intent,
    )
    assert result.is_valid is False


@pytest.mark.asyncio
async def test_pipeline_ambiguous_question_does_not_execute_sql():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    pipeline = QueryPipeline()
    with patch("backend.pipeline.query_pipeline.execution_service") as mock_execution:
        response = await pipeline.execute(
            PipelineRequest(
                question="لیست کارکنان یک مدرسه خاص را بده",
                tenant_id="education_ministry",
            )
        )
    assert response.needs_clarification is True
    assert response.sql is None
    mock_execution.execute.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_validation_failure_does_not_execute_sql():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline
    from backend.sql.models import GeneratedSQL

    pipeline = QueryPipeline()
    bad_sql = GeneratedSQL(
        sql="SELECT salary_items.missing_column FROM salary_items",
        explanation="bad",
        confidence=0.4,
    )
    with patch("backend.pipeline.query_pipeline.sql_generator.generate", AsyncMock(return_value=bad_sql)):
        with patch("backend.pipeline.query_pipeline.execution_service") as mock_execution:
            response = await pipeline.execute(
                PipelineRequest(
                    question="بیشترین حقوق پرداختی مربوط به چه کسی است؟",
                    tenant_id="education_ministry",
                )
            )
    assert response.success is False
    assert response.valid is False
    mock_execution.execute.assert_not_called()


@pytest.mark.asyncio
async def test_manual_student_count_pipeline():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    response = await QueryPipeline().execute(
        PipelineRequest(question="تعداد دانش آموزان کل کشور چقدر است؟", tenant_id="education_ministry")
    )
    assert response.group == "student"
    assert response.report == "student_list"
    assert "students" in (response.sql or "")
    assert response.valid is True


@pytest.mark.asyncio
async def test_manual_highest_salary_pipeline():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    response = await QueryPipeline().execute(
        PipelineRequest(question="بیشترین حقوق پرداختی مربوط به چه کسی است؟", tenant_id="education_ministry")
    )
    assert response.group == "salary"
    assert response.report == "salary_summary"
    assert "salary_items" in (response.sql or "")
    assert "employees" in (response.sql or "")
    assert "ORDER BY total_salary DESC" in (response.sql or "")
    assert "LIMIT 1" in (response.sql or "")
    assert response.valid is True


@pytest.mark.asyncio
async def test_manual_specific_school_asks_clarification():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    response = await QueryPipeline().execute(
        PipelineRequest(question="لیست کارکنان یک مدرسه خاص را بده", tenant_id="education_ministry")
    )
    assert response.needs_clarification is True
    assert response.sql is None


@pytest.mark.asyncio
async def test_manual_schools_by_province_pipeline():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    response = await QueryPipeline().execute(
        PipelineRequest(question="تعداد مدارس هر استان را مقایسه کن", tenant_id="education_ministry")
    )
    assert response.report == "school_statistics"
    assert "schools" in (response.sql or "")
    assert "organization_units" in (response.sql or "")
    assert "GROUP BY organization_units.province" in (response.sql or "")
    assert "ranking_requests" not in (response.sql or "")
    assert response.valid is True


@pytest.mark.asyncio
async def test_manual_unapproved_ranking_pipeline():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import QueryPipeline

    response = await QueryPipeline().execute(
        PipelineRequest(question="درخواست های رتبه بندی تایید نشده را نمایش بده", tenant_id="education_ministry")
    )
    assert response.report == "ranking_summary"
    assert "ranking_requests" in (response.sql or "")
    assert "status" in (response.sql or "").lower()


def test_grounded_answer_does_not_hallucinate():
    from backend.answer.generator import AnswerGenerator

    answer = AnswerGenerator()._deterministic_answer({
        "columns": ["count"],
        "rows": [{"count": 3}],
        "row_count": 1,
    })
    assert answer == "count: 3"
    assert "مدرسه" not in answer


# Phase 6 tests - SQL Execution
def test_execution_models():
    from backend.execution.models import QueryRequest, QueryResult
    
    request = QueryRequest(sql="SELECT 1")
    assert request.sql == "SELECT 1"
    assert request.timeout == 30
    assert request.max_rows == 1000
    
    result = QueryResult(success=True, columns=["id"], rows=[{"id": 1}], row_count=1)
    assert result.success is True
    assert result.row_count == 1


def test_execution_limiter_select_only():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("SELECT students.id FROM students LIMIT 1000")
    assert result.is_valid is True


def test_execution_limiter_rejects_select_star():
    from backend.execution.limiter import SQLLimiter

    limiter = SQLLimiter()
    result = limiter.validate_for_execution("SELECT * FROM students")
    assert result.is_valid is False
    assert any("SELECT *" in e for e in result.errors)


def test_execution_limiter_rejects_large_limit():
    from backend.execution.limiter import SQLLimiter

    limiter = SQLLimiter()
    result = limiter.validate_for_execution("SELECT students.id FROM students LIMIT 5000")
    assert result.is_valid is False
    assert any("LIMIT" in e for e in result.errors)


def test_execution_limiter_rejects_large_runtime_options():
    from backend.execution.limiter import SQLLimiter

    limiter = SQLLimiter()
    result = limiter.validate_for_execution("SELECT students.id FROM students", timeout=60, max_rows=5000)
    assert result.is_valid is False
    assert any("timeout" in e for e in result.errors)
    assert any("max_rows" in e for e in result.errors)


def test_execution_limiter_rejects_unbounded_multi_join_list():
    from backend.execution.limiter import SQLLimiter

    limiter = SQLLimiter()
    result = limiter.validate_for_execution(
        "SELECT students.id, schools.name, organization_units.province "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id"
    )
    assert result.is_valid is False
    assert any("multi-table" in e for e in result.errors)


def test_execution_limiter_rejects_drop():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("DROP TABLE students")
    assert result.is_valid is False
    assert any("DROP" in e for e in result.errors)


def test_execution_limiter_rejects_delete():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("DELETE FROM students")
    assert result.is_valid is False
    assert any("DELETE" in e for e in result.errors)


def test_execution_limiter_rejects_update():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("UPDATE students SET name='test'")
    assert result.is_valid is False


def test_execution_limiter_rejects_insert():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("INSERT INTO students VALUES (1)")
    assert result.is_valid is False


def test_execution_limiter_rejects_multiple_statements():
    from backend.execution.limiter import SQLLimiter
    
    limiter = SQLLimiter()
    result = limiter.validate_for_execution("SELECT 1; DROP TABLE students")
    assert result.is_valid is False


def test_api_execute_endpoint():
    from unittest.mock import patch, MagicMock
    from backend.execution.models import QueryResult
    
    mock_result = QueryResult(
        success=True,
        columns=["id", "name"],
        rows=[{"id": 1, "name": "test"}],
        row_count=1,
        execution_time_ms=10.5
    )
    
    with patch("backend.api.main.execution_service") as mock_service:
        mock_service.execute.return_value = mock_result
        response = client.post("/sql/execute", json={"sql": "SELECT 1"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["row_count"] == 1


def test_api_execute_rejects_forbidden():
    from backend.execution.models import QueryResult
    
    with patch("backend.api.main.execution_service") as mock_service:
        mock_result = QueryResult(
            success=False,
            error="کوئری DROP مجاز نیست",
            execution_time_ms=0
        )
        mock_service.execute.return_value = mock_result
        response = client.post("/sql/execute", json={"sql": "DROP TABLE students"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


# Phase 6.5 tests - Query Pipeline
def test_pipeline_models():
    from backend.pipeline.models import PipelineRequest, PipelineResponse, PipelineTrace
    
    request = PipelineRequest(question="test")
    assert request.question == "test"
    assert request.execute is True
    
    trace = PipelineTrace(steps=[], total_duration_ms=100.0, success=True)
    assert trace.success is True


def test_pipeline_trace():
    from backend.pipeline.trace import PipelineTracer
    
    tracer = PipelineTracer()
    tracer.add_step("step1", "success", 50.0)
    tracer.add_step("step2", "success", 30.0)
    
    trace = tracer.get_trace()
    assert len(trace.steps) == 2
    assert trace.success is True


def test_pipeline_trace_with_error():
    from backend.pipeline.trace import PipelineTracer
    
    tracer = PipelineTracer()
    tracer.add_step("step1", "success", 50.0)
    tracer.add_step("step2", "error", 30.0, error="test error")
    
    trace = tracer.get_trace()
    assert len(trace.steps) == 2
    assert trace.success is False


def test_api_query_endpoint():
    from unittest.mock import patch, AsyncMock
    from backend.pipeline.models import PipelineResponse, PipelineTrace
    
    mock_result = PipelineResponse(
        question="test",
        group="salary",
        group_name="گروه حقوق",
        report="salary_summary",
        report_name="خلاصه حقوق",
        sql="SELECT * FROM salary_items",
        valid=True,
        result={"columns": ["id"], "rows": [{"id": 1}], "row_count": 1},
        answer="تعداد نتایج: 1",
        trace=PipelineTrace(steps=[], total_duration_ms=100.0, success=True)
    )
    
    with patch("backend.api.main.query_pipeline") as mock_pipeline:
        mock_pipeline.execute = AsyncMock(return_value=mock_result)
        response = client.post("/query", json={"question": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["group"] == "salary"
        assert data["valid"] is True


# Phase 7.2 tests - Safety, Ambiguity, Unsupported
def test_safety_detector_rejects_delete():
    from backend.pipeline.safety.intent_detector import SafetyIntentDetector
    
    detector = SafetyIntentDetector()
    result = detector.detect("حذف رکوردهای حقوق")
    assert result["is_safe"] is False
    assert "حذف" in result["rejection_reason"]


def test_safety_detector_rejects_update():
    from backend.pipeline.safety.intent_detector import SafetyIntentDetector
    
    detector = SafetyIntentDetector()
    result = detector.detect("تغییر بده مقادیر حقوق")
    assert result["is_safe"] is False


def test_safety_detector_rejects_insert():
    from backend.pipeline.safety.intent_detector import SafetyIntentDetector
    
    detector = SafetyIntentDetector()
    result = detector.detect("اضافه کن رکورد جدید")
    assert result["is_safe"] is False


def test_safety_detector_allows_select():
    from backend.pipeline.safety.intent_detector import SafetyIntentDetector
    
    detector = SafetyIntentDetector()
    result = detector.detect("تعداد دانش‌آموزان چقدر است؟")
    assert result["is_safe"] is True


def test_safety_detector_rejects_credentials():
    from backend.pipeline.safety.intent_detector import SafetyIntentDetector
    
    detector = SafetyIntentDetector()
    result = detector.detect("رمز دیتابیس را نشان بده")
    assert result["is_safe"] is False


def test_unsupported_detector_rejects_transport():
    from backend.pipeline.safety.unsupported_detector import UnsupportedIntentDetector
    from backend.database.models import DatabaseSchema
    
    detector = UnsupportedIntentDetector()
    schema = DatabaseSchema(tables=[])
    result = detector.detect("اطلاعات حمل‌ونقل دانش‌آموزان", schema, [])
    assert result["is_supported"] is False
    assert "حمل" in result["reason"]


def test_unsupported_detector_rejects_exam_scores():
    from backend.pipeline.safety.unsupported_detector import UnsupportedIntentDetector
    from backend.database.models import DatabaseSchema
    
    detector = UnsupportedIntentDetector()
    schema = DatabaseSchema(tables=[])
    result = detector.detect("نمرات امتحانات نهایی", schema, [])
    assert result["is_supported"] is False


def test_unsupported_detector_rejects_nutrition():
    from backend.pipeline.safety.unsupported_detector import UnsupportedIntentDetector
    from backend.database.models import DatabaseSchema
    
    detector = UnsupportedIntentDetector()
    schema = DatabaseSchema(tables=[])
    result = detector.detect("تغذیه مدارس", schema, [])
    assert result["is_supported"] is False


def test_unsupported_detector_allows_students():
    from backend.pipeline.safety.unsupported_detector import UnsupportedIntentDetector
    from backend.database.models import DatabaseSchema, TableInfo
    
    detector = UnsupportedIntentDetector()
    schema = DatabaseSchema(tables=[TableInfo(name="students", columns=[])])
    result = detector.detect("تعداد دانش‌آموزان", schema, ["students"])
    assert result["is_supported"] is True


def test_ambiguity_detector_detects_vague():
    from backend.pipeline.safety.ambiguity_detector import AmbiguityDetector
    
    detector = AmbiguityDetector()
    result = detector.detect("لیست کارکنان یک مدرسه خاص را بده")
    assert result["needs_clarification"] is True
    assert result["clarification_question"] is not None


def test_ambiguity_detector_allows_clear():
    from backend.pipeline.safety.ambiguity_detector import AmbiguityDetector
    
    detector = AmbiguityDetector()
    result = detector.detect("تعداد دانش‌آموزان فعال")
    assert result["needs_clarification"] is False


def test_api_rejects_destructive():
    response = client.post("/query", json={"question": "حذف رکوردهای حقوق"})
    assert response.status_code == 200
    data = response.json()
    assert data["rejected"] is True
    assert data["sql"] is None


def test_api_rejects_update():
    response = client.post("/query", json={"question": "مقادیر حقوق همه کارکنان را تغییر بده"})
    assert response.status_code == 200
    data = response.json()
    assert data["rejected"] is True
    assert data["sql"] is None


def test_api_ambiguity_no_crash():
    response = client.post("/query", json={"question": "لیست کارکنان یک مدرسه خاص را بده"})
    assert response.status_code == 200
    data = response.json()
    assert data["needs_clarification"] is True
    assert data["sql"] is None
    assert data["result"] is None


def test_api_unsupported_transport():
    response = client.post("/query", json={"question": "اطلاعات حمل‌ونقل دانش‌آموزان"})
    assert response.status_code == 200
    data = response.json()
    assert data["unsupported"] is True
    assert data["sql"] is None


def test_api_unsupported_exam_scores():
    response = client.post("/query", json={"question": "نمرات امتحانات نهایی را نمایش بده"})
    assert response.status_code == 200
    data = response.json()
    assert data["unsupported"] is True
    assert data["sql"] is None


def test_api_unsupported_nutrition():
    response = client.post("/query", json={"question": "تغذیه مدارس"})
    assert response.status_code == 200
    data = response.json()
    assert data["unsupported"] is True
    assert data["sql"] is None


def test_pipeline_response_model_nullable():
    from backend.pipeline.models import PipelineResponse, PipelineTrace
    
    response = PipelineResponse(
        question="test",
        rejected=True,
        rejection_reason="test reason",
        trace=PipelineTrace()
    )
    assert response.rejected is True
    assert response.sql is None
    assert response.result is None
    assert response.group is None


def test_api_student_count():
    response = client.post("/query", json={"question": "تعداد کل دانش‌آموزان فعال"})
    assert response.status_code == 200
    data = response.json()
    assert data["group"] == "student"


def test_api_salary_highest():
    response = client.post("/query", json={"question": "بیشترین حقوق پرداختی مربوط به چه کسی است؟"})
    assert response.status_code == 200
    data = response.json()
    assert data["group"] == "salary"


# Phase 7 tests - Answer Generation
def test_answer_models():
    from backend.answer.models import AnswerRequest, AnswerResponse, FormattedResult
    
    request = AnswerRequest(
        question="test",
        result={"columns": ["id"], "rows": [{"id": 1}], "row_count": 1}
    )
    assert request.question == "test"
    
    response = AnswerResponse(answer="پاسخ تست", confidence=0.9)
    assert response.answer == "پاسخ تست"


def test_result_formatter_empty():
    from backend.answer.formatter import ResultFormatter
    
    formatter = ResultFormatter()
    result = formatter.format_result({})
    assert result.display_type == "empty"
    assert "یافت نشد" in result.summary


def test_result_formatter_single_value():
    from backend.answer.formatter import ResultFormatter
    
    formatter = ResultFormatter()
    result = formatter.format_result({
        "columns": ["count"],
        "rows": [{"count": 100}],
        "row_count": 1
    })
    assert result.display_type == "single"
    assert "100" in result.summary


def test_result_formatter_table():
    from backend.answer.formatter import ResultFormatter
    
    formatter = ResultFormatter()
    result = formatter.format_result({
        "columns": ["id", "name"],
        "rows": [
            {"id": 1, "name": "علی"},
            {"id": 2, "name": "محمد"},
            {"id": 3, "name": "فاطمه"}
        ],
        "row_count": 3
    })
    assert result.display_type == "table"
    assert result.total == 3


def test_prompt_builder():
    from backend.answer.prompt_builder import AnswerPromptBuilder
    from backend.answer.models import AnswerRequest, FormattedResult
    
    builder = AnswerPromptBuilder()
    request = AnswerRequest(
        question="تعداد دانش‌آموزان",
        result={"columns": ["count"], "rows": [{"count": 50}], "row_count": 1},
        report_name="آمار مدارس",
        group_name="گروه دانش‌آموزان"
    )
    formatted = FormattedResult(display_type="single", summary="نتیجه: 50")
    
    prompt = builder.build_prompt(request, formatted)
    assert "تعداد دانش‌آموزان" in prompt
    assert "آمار مدارس" in prompt
    assert "50" in prompt


# Phase 7.3.1 tests - multi-intent policy, references, salary phrases
def test_phase_731_salary_base_phrase_not_multi_intent():
    from backend.pipeline.safety.multi_intent_detector import multi_intent_detector
    from backend.pipeline.intent import extract_intent

    question = "تفاوت حقوق پایه و خالص پرداختی"
    detection = multi_intent_detector.detect(question)
    intent = extract_intent(question)

    assert detection["multi_intent"] is False
    assert detection["detected_entities"] == ["salary"]
    assert intent.requested_entity == "salary"


def test_phase_731_composable_multi_intent_policy():
    from backend.pipeline.safety.multi_intent_detector import multi_intent_detector

    province = multi_intent_detector.detect("تعداد کارکنان و دانش‌آموزان هر استان")
    region = multi_intent_detector.detect("تعداد مدارس و دانش‌آموزان هر منطقه")
    independent = multi_intent_detector.detect("تعداد کارکنان را بگو و بیشترین حقوق را هم نشان بده")

    assert province["multi_intent"] is True
    assert province["is_composable"] is True
    assert province["shared_grouping_dimension"] == "province"
    assert province["needs_clarification"] is False

    assert region["multi_intent"] is True
    assert region["is_composable"] is True
    assert region["shared_grouping_dimension"] == "city"
    assert region["needs_clarification"] is False

    assert independent["multi_intent"] is True
    assert independent["is_composable"] is False
    assert independent["needs_clarification"] is True


def test_phase_731_referential_ambiguity_patterns():
    from backend.pipeline.intent import detect_ambiguity

    region = detect_ambiguity("آمار این منطقه را نشان بده")
    school = detect_ambiguity("دانش‌آموزان آن مدرسه را نمایش بده")

    assert region.needs_clarification is True
    assert "منطقه" in region.clarification_question
    assert school.needs_clarification is True
    assert "مدرسه" in school.clarification_question


@pytest.mark.asyncio
async def test_phase_731_pipeline_composable_queries_generate_safe_sql():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    province = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارکنان و دانش‌آموزان هر استان", execute=False)
    )
    region = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس و دانش‌آموزان هر منطقه", execute=False)
    )

    assert province.needs_clarification is False
    assert province.group == "student"
    assert province.report == "school_statistics"
    assert province.valid is True
    assert "employee_count" in province.sql
    assert "student_count" in province.sql
    assert "WHERE eu.province = ou.province" in province.sql

    assert region.needs_clarification is False
    assert region.group == "student"
    assert region.report == "school_statistics"
    assert region.valid is True
    assert "school_count" in region.sql
    assert "student_count" in region.sql
    assert "WHERE su.city = ou.city" in region.sql


@pytest.mark.asyncio
async def test_phase_731_pipeline_referential_ambiguity_blocks_sql():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    region = await query_pipeline.execute(PipelineRequest(question="آمار این منطقه را نشان بده"))
    school = await query_pipeline.execute(PipelineRequest(question="دانش‌آموزان آن مدرسه را نمایش بده"))

    assert region.needs_clarification is True
    assert region.sql is None
    assert school.needs_clarification is True
    assert school.sql is None


@pytest.mark.asyncio
async def test_phase_731_pipeline_salary_service_payment_maps_to_retirement_pension():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="برای کدام کارمند بیشترین سنوات پرداخت شده؟", execute=False)
    )

    assert response.group == "employee"
    assert response.report == "employee_list"
    assert response.valid is True
    assert response.intent["requested_entity"] == "retirement"
    assert response.intent["ranking_metric"] == "pension_amount"
    assert "FROM retirement_records" in response.sql
    assert "retirement_records.pension_amount" in response.sql
    assert "ORDER BY retirement_records.pension_amount DESC" in response.sql
    assert "LIMIT 1" in response.sql
    assert "salary_items" not in response.sql


@pytest.mark.asyncio
async def test_phase_731_pipeline_lowest_salary_service_payment_maps_to_retirement_pension():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="برای کدام کارمند کمترین سنوات پرداخت شده؟", execute=False)
    )

    assert response.group == "employee"
    assert response.report == "employee_list"
    assert response.valid is True
    assert response.intent["requested_entity"] == "retirement"
    assert response.intent["ranking_metric"] == "pension_amount"
    assert "FROM retirement_records" in response.sql
    assert "retirement_records.pension_amount" in response.sql
    assert "ORDER BY retirement_records.pension_amount ASC" in response.sql
    assert "LIMIT 1" in response.sql
    assert "salary_items" not in response.sql


@pytest.mark.asyncio
async def test_employee_count_for_specific_province_uses_employee_join():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد کارمندان استان اصفهان را نشان بده", execute=False)
    )

    assert response.group == "employee"
    assert response.report == "employee_statistics"
    assert response.valid is True
    assert "COUNT(employees.id) AS employee_count" in response.sql
    assert "JOIN organization_units" in response.sql
    assert "organization_units.province = 'اصفهان'" in response.sql


@pytest.mark.asyncio
async def test_student_count_for_specific_province_uses_school_org_join():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان استان تهران", execute=False)
    )

    assert response.group == "student"
    assert response.valid is True
    assert "COUNT(students.id) AS student_count" in response.sql
    assert "JOIN schools" in response.sql
    assert "JOIN organization_units" in response.sql
    assert "organization_units.province = 'تهران'" in response.sql


@pytest.mark.asyncio
async def test_student_count_for_specific_province_and_first_name():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد دانش آموزان تهران که اسم آن ها پوریا هست را بگو", execute=False)
    )

    assert response.group == "student"
    assert response.valid is True
    assert response.intent["province"] == "تهران"
    assert response.intent["named_student"] == "پوریا"
    assert "organization_units.province = 'تهران'" in response.sql
    assert "students.first_name = 'پوریا'" in response.sql


@pytest.mark.asyncio
async def test_school_names_for_specific_province_use_schools_table():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="اسم مدارس استان تهران", execute=False)
    )

    assert response.group == "student"
    assert response.report == "school_statistics"
    assert response.valid is True
    assert "SELECT schools.id, schools.name" in response.sql
    assert "FROM schools" in response.sql
    assert "JOIN organization_units" in response.sql
    assert "organization_units.province = 'تهران'" in response.sql
    assert "FROM organization_units" not in response.sql


@pytest.mark.asyncio
async def test_school_count_for_specific_province_returns_count_not_names():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس استان تهران", execute=False)
    )

    assert response.group == "student"
    assert response.report == "school_statistics"
    assert response.valid is True
    assert "COUNT(DISTINCT schools.id) AS school_count" in response.sql
    assert "organization_units.province = 'تهران'" in response.sql
    assert "SCHOOL_NAMES_BY_PROVINCE" not in response.sql


@pytest.mark.asyncio
async def test_school_phone_by_exact_name():
    from backend.pipeline.models import PipelineRequest
    from backend.pipeline.query_pipeline import query_pipeline

    response = await query_pipeline.execute(
        PipelineRequest(question="شماره تلفن دبیرستان شهید بهشتی", execute=False)
    )

    assert response.group == "student"
    assert response.report == "school_statistics"
    assert response.valid is True
    assert response.intent["named_school"] == "دبیرستان شهید بهشتی"
    assert "SELECT schools.name, schools.phone" in response.sql
    assert "schools.name = 'دبیرستان شهید بهشتی'" in response.sql
