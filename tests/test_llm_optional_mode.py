import pytest

from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.services.llm_service import LLMService
from backend.sql.generator import SQLGenerator
from backend.sql.models import SQLPlan


@pytest.mark.asyncio
async def test_llm_service_does_not_connect_when_disabled(monkeypatch):
    service = LLMService()
    monkeypatch.setattr(service.settings, "llm_enabled", False)

    assert await service.is_connected() is False
    assert await service.list_models() == []
    with pytest.raises(RuntimeError, match="disabled"):
        await service.chat("hello")


@pytest.mark.asyncio
async def test_sql_generator_returns_clean_failure_when_llm_disabled_without_template(monkeypatch):
    generator = SQLGenerator()
    monkeypatch.setattr(generator.settings, "llm_enabled", False)
    schema = DatabaseSchema(
        tables=[
            TableInfo(
                name="unknown_table",
                columns=[ColumnInfo(name="id", data_type="integer")],
            )
        ]
    )

    generated = await generator.generate(
        SQLPlan(required_tables=["unknown_table"], selected_columns=["UNSUPPORTED_TEMPLATE_MARKER"]),
        schema,
    )

    assert generated.sql == ""
    assert "حالت سبک" in generated.explanation
    assert generated.confidence == 0.0
    assert generated.generation_source == "llm_disabled"


def test_dashboard_mentions_lightweight_ollama_optional_mode():
    from pathlib import Path

    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "اختیاری / حالت سبک" in html
    assert "Ollama فقط در حالت مدل زبانی لازم است" in html
    assert "SQL source" in html
    assert "lightweight: no LLM" in html


def test_health_reports_lightweight_mode_when_llm_disabled(monkeypatch):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main.settings, "llm_enabled", False)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] == "lightweight"
    assert data["llm_enabled"] is False
    assert data["llm_required"] is False
