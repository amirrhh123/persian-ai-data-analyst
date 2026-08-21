"""Tests for query-level source citations."""

from backend.citations.service import CitationService
from backend.pipeline.models import PipelineStep, PipelineTrace


def test_builds_database_semantic_and_retrieval_citations() -> None:
    trace = PipelineTrace(steps=[
        PipelineStep(
            name="group_retrieval",
            status="success",
            data={
                "retrieval_mode": "hybrid_reranked",
                "hybrid_score": 0.74,
                "reranker_score": 0.82,
                "confidence_gate": {"accepted": True, "margin": 0.18},
            },
        ),
        PipelineStep(
            name="report_retrieval",
            status="success",
            data={"retrieval_mode": "hybrid_reranked", "vector_score": 0.78},
        ),
    ])
    citation = CitationService().build(
        database="persian_ai_db",
        tenant_id="education_ministry",
        sql=(
            "SELECT students.id, schools.name FROM students "
            "JOIN schools ON students.school_id = schools.id "
            "WHERE schools.name = 'دبیرستان فرزانگان'"
        ),
        group_id="student",
        report_id="student_list",
        generation_source="template",
        trace=trace,
    )

    assert citation.scope == "query_level"
    assert citation.tables == ["students", "schools"]
    assert "students.id" in citation.columns
    assert "schools.name" in citation.columns
    assert "دبیرستان فرزانگان" not in citation.sql_preview
    assert "'***'" in citation.sql_preview
    assert {source.source_type for source in citation.sources} == {
        "database_table", "semantic_group", "semantic_report",
        "sql_generation", "retrieval_evidence",
    }


def test_redacts_unquoted_ten_digit_identifier() -> None:
    citation = CitationService().build(
        database="db",
        tenant_id="tenant",
        sql="SELECT employees.id FROM employees WHERE national_id = 4871587050",
        group_id=None,
        report_id=None,
        generation_source=None,
        trace=PipelineTrace(),
    )
    assert "4871587050" not in citation.sql_preview
    assert "***" in citation.sql_preview


def test_handles_response_without_sql() -> None:
    citation = CitationService().build(
        database="db",
        tenant_id="tenant",
        sql=None,
        group_id=None,
        report_id=None,
        generation_source=None,
        trace=PipelineTrace(),
    )
    assert citation.tables == []
    assert citation.columns == []
    assert citation.sql_preview is None
    assert citation.sources == []
