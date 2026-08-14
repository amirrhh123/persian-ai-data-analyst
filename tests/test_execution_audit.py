import json
from unittest.mock import MagicMock

from backend.execution.audit import QueryAuditLogger
from backend.execution.models import QueryRequest
from backend.execution.service import ExecutionService


def test_query_audit_logger_redacts_literals_and_national_ids(tmp_path):
    logger = QueryAuditLogger(tmp_path / "audit.jsonl")

    event = logger.log(
        sql="SELECT employees.id FROM employees WHERE employees.national_id = '8223876400' "
        "AND employees.first_name = \"Nasrin\"",
        status="success",
        row_count=1,
    )

    assert event["sql"] == (
        "SELECT employees.id FROM employees WHERE employees.national_id = '***' "
        'AND employees.first_name = "***"'
    )
    assert "8223876400" not in event["sql"]
    assert "Nasrin" not in event["sql"]

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_id"] == event["event_id"]


def test_execution_service_logs_rejected_queries(tmp_path):
    service = ExecutionService()
    service.audit_logger = QueryAuditLogger(tmp_path / "audit.jsonl")

    result = service.execute(QueryRequest(sql="SELECT * FROM students"))

    assert result.success is False
    event = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert event["status"] == "rejected"
    assert event["errors"]


def test_execution_service_logs_successful_queries(tmp_path):
    service = ExecutionService()
    service.audit_logger = QueryAuditLogger(tmp_path / "audit.jsonl")
    service.connection = MagicMock()
    service.connection.execute_query.return_value = {
        "columns": ["id"],
        "rows": [{"id": 1}],
        "row_count": 1,
        "execution_time_ms": 12.5,
        "truncated": False,
    }

    result = service.execute(QueryRequest(sql="SELECT students.id FROM students LIMIT 1000"))

    assert result.success is True
    event = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert event["status"] == "success"
    assert event["row_count"] == 1
    assert event["execution_time_ms"] == 12.5


def test_query_audit_logger_summarizes_recent_events(tmp_path):
    logger = QueryAuditLogger(tmp_path / "audit.jsonl")
    logger.log(sql="SELECT students.id FROM students LIMIT 1000", status="success", row_count=2, execution_time_ms=10)
    logger.log(sql="SELECT * FROM students", status="rejected", errors=["SELECT *"], execution_time_ms=0)
    logger.log(sql="SELECT students.id FROM students LIMIT 1000", status="error", errors=["boom"], execution_time_ms=0)

    summary = logger.summarize()

    assert summary["total_events"] == 3
    assert summary["success_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["error_count"] == 1
    assert summary["total_rows_returned"] == 2
    assert summary["avg_execution_time_ms"] == 3.33
    assert len(summary["recent_events"]) == 3


def test_sql_audit_summary_endpoint(monkeypatch, tmp_path):
    from backend.api import main
    from backend.api.main import app
    from fastapi.testclient import TestClient

    logger = QueryAuditLogger(tmp_path / "audit.jsonl")
    logger.log(sql="SELECT students.id FROM students LIMIT 1000", status="success", row_count=1, execution_time_ms=5)
    monkeypatch.setattr(main, "query_audit_logger", logger)

    response = TestClient(app).get("/sql/audit/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    assert data["success_count"] == 1
    assert data["recent_events"][0]["sql"] == "SELECT students.id FROM students LIMIT 1000"
