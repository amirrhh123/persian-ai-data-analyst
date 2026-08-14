"""Behavior tests for Persian hybrid retrieval."""

from types import SimpleNamespace

from backend.knowledge.models import Report
from backend.reports.group_models import ReportGroup
from backend.reports.group_retriever import GroupRetriever
from backend.reports.hybrid_retrieval import HybridCandidate, HybridRetriever
from backend.reports.retriever import ReportRetriever


def test_normalization_unifies_persian_variants_and_digits() -> None:
    retriever = HybridRetriever()

    assert retriever.tokenize("كلاس يازدهم ۱۲۳") == retriever.tokenize(
        "کلاس یازدهم 123"
    )


def test_lexical_search_prefers_exact_identifier_and_phrase() -> None:
    retriever = HybridRetriever(vector_weight=0.55, lexical_weight=0.45)
    candidates = [
        HybridCandidate(
            id="salary",
            document="گزارش خلاصه پرداخت حقوق و مزایا",
            metadata={"report_id": "salary_summary"},
        ),
        HybridCandidate(
            id="employee",
            document="اطلاعات کارمندان و فهرست پرسنل",
            metadata={"report_id": "employee_list"},
        ),
    ]

    ranked = retriever.rank(
        query="گزارش salary_summary",
        candidates=candidates,
        vector_scores={"employee": 0.60, "salary": 0.58},
    )

    assert ranked[0].candidate.id == "salary"
    assert ranked[0].lexical_score > ranked[1].lexical_score


def test_hybrid_search_combines_semantic_and_lexical_evidence() -> None:
    retriever = HybridRetriever(vector_weight=0.60, lexical_weight=0.40)
    candidates = [
        HybridCandidate(
            id="student",
            document="آمار دانش آموزان مدارس",
            metadata={},
        ),
        HybridCandidate(
            id="employee",
            document="فهرست کارکنان و اطلاعات کارمندان",
            metadata={},
        ),
    ]

    ranked = retriever.rank(
        query="اطلاعات کارمندان",
        candidates=candidates,
        vector_scores={"student": 0.70, "employee": 0.62},
    )

    assert ranked[0].candidate.id == "employee"
    assert ranked[0].final_score > ranked[1].final_score
    assert 0.0 <= ranked[0].final_score <= 1.0


def test_hybrid_search_returns_empty_list_for_empty_candidates() -> None:
    retriever = HybridRetriever()

    assert retriever.rank("دانش آموز", [], {}) == []


class _FakeCollection:
    def __init__(self, results: dict[str, list[list[object]]]) -> None:
        self.results = results

    def query(self, **_: object) -> dict[str, list[list[object]]]:
        return self.results


def test_group_retriever_uses_hybrid_ranking(monkeypatch) -> None:
    groups = [
        ReportGroup(
            id="student",
            name="دانش آموزان",
            description="آمار مدارس",
        ),
        ReportGroup(
            id="employee",
            name="کارمندان",
            description="اطلاعات کارکنان",
            keywords=["کد پرسنلی"],
        ),
    ]
    collection = _FakeCollection(
        {
            "ids": [["tenant_group_student", "tenant_group_employee"]],
            "documents": [["آمار مدارس", "اطلاعات کارکنان کد پرسنلی"]],
            "metadatas": [[
                {"group_id": "student", "group_name": "دانش آموزان"},
                {"group_id": "employee", "group_name": "کارمندان"},
            ]],
            "distances": [[0.30, 0.38]],
        }
    )
    fake_client = SimpleNamespace(get_collection=lambda _: collection)

    monkeypatch.setattr(
        "backend.reports.group_retriever.embedding_service.embed_text",
        lambda _: [0.1],
    )
    monkeypatch.setattr(
        "backend.reports.group_retriever.vector_store._get_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "backend.reports.group_retriever.GroupLoader.load_all_groups",
        lambda _: groups,
    )

    result = GroupRetriever().search_groups("tenant", "کد پرسنلی")

    assert result["group_id"] == "employee"
    assert result["retrieval_mode"] == "hybrid_reranked"
    assert result["reranker_score"] > 0
    assert result["confidence_gate"]["accepted"] is True
    assert result["query_decomposition"]["decomposed"] is False
    assert result["top_candidates"][0]["lexical_score"] > 0


def test_report_retriever_uses_hybrid_ranking(monkeypatch) -> None:
    reports = [
        Report(
            id="student_list",
            name="فهرست دانش آموزان",
            description="اطلاعات مدارس",
            linked_table="students",
            group_id="student",
        ),
        Report(
            id="employee_list",
            name="فهرست کارمندان",
            description="اطلاعات کارکنان",
            linked_table="employees",
            group_id="employee",
            example_questions=["کد پرسنلی کارمند"],
        ),
    ]
    collection = _FakeCollection(
        {
            "ids": [["tenant_student_list", "tenant_employee_list"]],
            "documents": [["اطلاعات مدارس", "کد پرسنلی کارمند"]],
            "metadatas": [[
                {"report_id": "student_list", "report_name": "دانش آموزان"},
                {"report_id": "employee_list", "report_name": "کارمندان"},
            ]],
            "distances": [[0.30, 0.38]],
        }
    )

    monkeypatch.setattr(
        "backend.reports.retriever.embedding_service.embed_text",
        lambda _: [0.1],
    )
    monkeypatch.setattr(
        "backend.reports.retriever.vector_store.get_collection",
        lambda _: collection,
    )
    monkeypatch.setattr(
        "backend.reports.retriever.KnowledgeLoader.load_all_reports",
        lambda _: reports,
    )
    monkeypatch.setattr(
        "backend.reports.retriever.KnowledgeLoader.load_metrics", lambda _: []
    )
    monkeypatch.setattr(
        "backend.reports.retriever.KnowledgeLoader.load_rules", lambda _: []
    )

    result = ReportRetriever().search_reports("tenant", "کد پرسنلی کارمند")

    assert result["report_id"] == "employee_list"
    assert result["retrieval_mode"] == "hybrid_reranked"
    assert result["reranker_score"] > 0
    assert result["confidence_gate"]["accepted"] is True
    assert result["query_decomposition"]["decomposed"] is False
    assert result["lexical_score"] > 0
