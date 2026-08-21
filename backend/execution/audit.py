import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from backend.config import get_settings


class QueryAuditLogger:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or Path("logs") / "execution_audit.jsonl"

    def log(
        self,
        *,
        sql: str,
        status: str,
        errors: list[str] | None = None,
        row_count: int | None = None,
        execution_time_ms: float | None = None,
        truncated: bool | None = None,
        timeout: int | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "sql": self._redact_sql(sql),
            "errors": errors or [],
            "row_count": row_count,
            "execution_time_ms": execution_time_ms,
            "truncated": truncated,
            "timeout": timeout,
            "max_rows": max_rows,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def summarize(self, limit: int = 1000) -> dict[str, Any]:
        if not self.log_path.exists():
            return self._empty_summary()

        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        selected_lines = lines[-max(1, min(limit, 10000)) :]
        events = []
        for line in selected_lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        summary = self._empty_summary()
        summary["total_events"] = len(events)
        summary["window_limit"] = limit
        if not events:
            return summary

        execution_times = [
            float(event["execution_time_ms"])
            for event in events
            if event.get("execution_time_ms") is not None
        ]
        row_counts = [
            int(event["row_count"])
            for event in events
            if event.get("row_count") is not None
        ]

        for event in events:
            status = event.get("status", "unknown")
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
            if event.get("truncated") is True:
                summary["truncated_events"] += 1

        summary["success_count"] = summary["by_status"].get("success", 0)
        summary["rejected_count"] = summary["by_status"].get("rejected", 0)
        summary["error_count"] = summary["by_status"].get("error", 0)
        summary["avg_execution_time_ms"] = round(sum(execution_times) / len(execution_times), 2) if execution_times else 0
        summary["max_execution_time_ms"] = round(max(execution_times), 2) if execution_times else 0
        summary["total_rows_returned"] = sum(row_counts)
        summary["last_event_at"] = events[-1].get("timestamp")
        summary["recent_events"] = events[-10:]
        return summary

    def _redact_sql(self, sql: str) -> str:
        if not get_settings().data_masking_enabled:
            return sql
        redacted = re.sub(r"'(?:''|[^'])*'", "'***'", sql)
        redacted = re.sub(r'"(?:""|[^"])*"', '"***"', redacted)
        redacted = re.sub(r"\b\d{10}\b", "***", redacted)
        return redacted

    def _empty_summary(self) -> dict[str, Any]:
        return {
            "total_events": 0,
            "window_limit": 0,
            "success_count": 0,
            "rejected_count": 0,
            "error_count": 0,
            "by_status": {},
            "avg_execution_time_ms": 0,
            "max_execution_time_ms": 0,
            "total_rows_returned": 0,
            "truncated_events": 0,
            "last_event_at": None,
            "recent_events": [],
        }


query_audit_logger = QueryAuditLogger()
