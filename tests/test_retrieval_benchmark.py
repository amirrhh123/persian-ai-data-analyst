import json
from pathlib import Path
from backend.retrieval_benchmark.service import RetrievalBenchmarkService

def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([
        {"id":"a","question":"دانش آموزان","expected_group":"student","expected_report":"student_list"},
        {"id":"b","question":"حقوق","expected_group":"salary","expected_report":"salary_summary"}
    ], ensure_ascii=False), encoding="utf-8")
    return path

def test_benchmark_calculates_top_k_mrr_and_latency(tmp_path: Path):
    def ranker(case, tenant_id, top_k):
        assert tenant_id == "tenant"
        expected = case.expected_report or case.expected_group
        return [expected] if case.id == "a" else ["wrong", expected]
    result = RetrievalBenchmarkService().run("tenant", 2, .5, dataset(tmp_path), ranker)
    assert result.status == "passed" and result.overall_top1_accuracy == .5
    assert result.group.top_k_accuracy == 1 and result.report.mrr == .75
    assert all(item.latency_ms >= 0 for item in result.cases)

def test_benchmark_fails_quality_gate_and_records_errors(tmp_path: Path):
    def broken(case, tenant_id, top_k):
        if case.id == "a": raise RuntimeError("retriever unavailable")
        return []
    result = RetrievalBenchmarkService().run("tenant", dataset_path=dataset(tmp_path), ranker=broken)
    assert result.status == "failed" and result.overall_top1_accuracy == 0
    assert any(item.error == "retriever unavailable" for item in result.cases)

def test_versioned_dataset_covers_groups_and_reports():
    cases = RetrievalBenchmarkService().load_cases()
    assert len(cases) >= 8
    assert {case.expected_group for case in cases} >= {"student", "employee", "salary"}
    assert all(case.expected_report for case in cases)
