"""Deterministic retrieval evaluation with Top-k, MRR, and latency metrics."""
import json
from pathlib import Path
from time import perf_counter
from typing import Callable
from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever
from backend.retrieval_benchmark.models import RetrievalBenchmarkCase, RetrievalBenchmarkResult, RetrievalCaseResult, RetrievalMetrics

Ranker = Callable[[RetrievalBenchmarkCase, str, int], list[str]]

class RetrievalBenchmarkService:
    def __init__(self, default_dataset: Path | None = None) -> None:
        self.default_dataset = default_dataset or Path(__file__).parent.parent.parent / "tests" / "benchmark" / "retrieval_cases.json"

    def load_cases(self, path: Path | None = None) -> list[RetrievalBenchmarkCase]:
        return [RetrievalBenchmarkCase.model_validate(item) for item in json.loads((path or self.default_dataset).read_text(encoding="utf-8"))]

    @staticmethod
    def _rank(expected: str, ranked_ids: list[str]) -> int | None:
        try: return ranked_ids.index(expected) + 1
        except ValueError: return None

    @staticmethod
    def _metrics(results: list[RetrievalCaseResult]) -> RetrievalMetrics:
        count = len(results)
        if not count: return RetrievalMetrics(evaluated=0, top1_accuracy=0, top_k_accuracy=0, mrr=0, average_latency_ms=0)
        return RetrievalMetrics(evaluated=count, top1_accuracy=round(sum(x.passed_top1 for x in results)/count,4), top_k_accuracy=round(sum(x.passed_top_k for x in results)/count,4), mrr=round(sum(1/x.rank if x.rank else 0 for x in results)/count,4), average_latency_ms=round(sum(x.latency_ms for x in results)/count,2))

    @staticmethod
    def _default_ranker(case: RetrievalBenchmarkCase, tenant_id: str, top_k: int) -> list[str]:
        if case.expected_report is None:
            result = group_retriever.search_groups(tenant_id, case.question, n_results=top_k)
            return [str(item["group_id"]) for item in result.get("top_candidates", [])]
        result = report_retriever.search_reports(tenant_id, case.question, n_results=top_k, group_filter=case.expected_group)
        return [str(item["report_id"]) for item in result.get("top_candidates", [])]

    def run(self, tenant_id: str, top_k: int = 3, minimum_top1: float = .80, dataset_path: Path | None = None, ranker: Ranker | None = None) -> RetrievalBenchmarkResult:
        rank_candidates = ranker or self._default_ranker
        results = []
        for case in self.load_cases(dataset_path):
            levels = [("group", case.expected_group)] + ([("report", case.expected_report)] if case.expected_report else [])
            for level, expected in levels:
                current = case if level == "report" else case.model_copy(update={"expected_report": None})
                started, error = perf_counter(), None
                try: ranked_ids = rank_candidates(current, tenant_id, top_k)[:top_k]
                except Exception as exc: ranked_ids, error = [], str(exc)
                rank = self._rank(expected, ranked_ids)
                results.append(RetrievalCaseResult(id=case.id, question=case.question, level=level, expected=expected, ranked_ids=ranked_ids, rank=rank, passed_top1=rank==1, passed_top_k=rank is not None and rank<=top_k, latency_ms=round((perf_counter()-started)*1000,2), error=error))
        group = self._metrics([x for x in results if x.level=="group"])
        report = self._metrics([x for x in results if x.level=="report"])
        overall = round(sum(x.passed_top1 for x in results)/len(results),4) if results else 0
        return RetrievalBenchmarkResult(status="passed" if overall>=minimum_top1 else "failed", tenant_id=tenant_id, top_k=top_k, minimum_top1=minimum_top1, group=group, report=report, overall_top1_accuracy=overall, cases=results)

retrieval_benchmark_service = RetrievalBenchmarkService()
