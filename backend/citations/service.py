"""Build source citations from executed pipeline evidence."""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.pipeline.models import CitationView, PipelineTrace, SourceCitation


_IDENTIFIER = r"[a-z_][a-z0-9_]*"


class CitationService:
    """Create query-level provenance without relying on generated prose."""

    @staticmethod
    def _tables(sql: str) -> list[str]:
        return list(dict.fromkeys(
            match.group(1).lower()
            for match in re.finditer(rf"\b(?:FROM|JOIN)\s+({_IDENTIFIER})", sql, re.I)
        ))

    @staticmethod
    def _columns(sql: str) -> list[str]:
        return list(dict.fromkeys(
            f"{match.group(1).lower()}.{match.group(2).lower()}"
            for match in re.finditer(rf"\b({_IDENTIFIER})\.({_IDENTIFIER})\b", sql, re.I)
        ))

    @staticmethod
    def _redact_sql(sql: str) -> str:
        redacted = re.sub(r"'(?:''|[^'])*'", "'***'", sql)
        return re.sub(r"\b[0-9۰-۹]{10}\b", "***", redacted)

    @staticmethod
    def _step_data(trace: PipelineTrace, name: str) -> dict[str, Any]:
        for step in trace.steps:
            if step.name == name and step.data:
                return step.data
        return {}

    def build(self, *, database: str, tenant_id: str, sql: Optional[str],
              group_id: Optional[str], report_id: Optional[str],
              generation_source: Optional[str], trace: PipelineTrace) -> CitationView:
        sql_text = sql or ""
        tables = self._tables(sql_text)
        columns = self._columns(sql_text)
        sources = [
            SourceCitation(
                source_type="database_table",
                label=f"PostgreSQL table: {table}",
                identifier=table,
                details={"database": database, "tenant_id": tenant_id},
            ) for table in tables
        ]
        if group_id:
            sources.append(SourceCitation(
                source_type="semantic_group", label="Semantic group", identifier=group_id,
            ))
        if report_id:
            sources.append(SourceCitation(
                source_type="semantic_report", label="Semantic report", identifier=report_id,
            ))
        if generation_source:
            sources.append(SourceCitation(
                source_type="sql_generation", label="SQL generation source",
                identifier=generation_source,
            ))

        group_retrieval = self._step_data(trace, "group_retrieval")
        report_retrieval = self._step_data(trace, "report_retrieval")
        retrieval_details: dict[str, Any] = {}
        for key in ("retrieval_mode", "vector_score", "lexical_score", "hybrid_score",
                    "reranker_score", "confidence_gate", "query_decomposition"):
            if key in group_retrieval:
                retrieval_details[f"group_{key}"] = group_retrieval[key]
            if key in report_retrieval:
                retrieval_details[f"report_{key}"] = report_retrieval[key]
        if retrieval_details:
            sources.append(SourceCitation(
                source_type="retrieval_evidence", label="Retrieval evidence",
                identifier="hybrid_pipeline", details=retrieval_details,
            ))

        return CitationView(
            database=database, tenant_id=tenant_id, tables=tables, columns=columns,
            sql_preview=self._redact_sql(sql_text) if sql_text else None,
            sources=sources,
        )


citation_service = CitationService()
