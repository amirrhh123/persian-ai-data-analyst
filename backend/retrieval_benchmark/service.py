"""Deterministic retrieval evaluation with Top-k, MRR, and latency metrics."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Callable

from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever
from backend.retrieval_benchmark.models import (
    RetrievalBenchmarkCase,
    RetrievalBenchmarkResult,
    RetrievalCaseResult,
    RetrievalMetrics,
)

Ranker = Callable[[RetrievalBenchmarkCase, str, int], list[str]]


class RetrievalBenchmarkService:
    def __init__(self, default_dataset: Path | None = None) -> None:
        self.default_dataset = default_dataset or (
            Path(__file__).parent.parent.parent / "tests" / "benchmark" / "retrieval_cases.json"
        )

    def load_cases(self, path: Path | None = None) -> list[RetrievalBenchmarkCase]:
        source = path or self.default_dataset
        payload = json.loads(source.read_text(encoding="utf-8"))
        return [RetrievalBenchmarkCase.model_validate(item) for item in payload]

    @staticmethod
    def _rank(expected: str, ranked_ids: list[str]) -> int | None:
        try:
            return ranked_ids.index(expected) + 1
        except ValueError:
            return None

    @staticmethod
    def _metrics(results: list[RetrievalCaseResult]) -> RetrievalMetrics:
        count = len(results)
        if not count:
            return RetrievalMetrics(evaluated=0, top1_accuracy=0, top_k_accuracy=0, mrr=0, average_latency_ms=0)
        return RetrievalMetrics(
            evaluated=count,
            top1_accuracy=round(sum(item.passed_top1 for item in results) / count, 4),
            top_k_accuracy=round(sum(item.passed_top_k for item in results) / count, 4),
            mrr=round(sum(1 / item.rank if item.rank else 0 for item in results) / count, 4),
            average_latency_ms=round(sum(item.latency_ms for item in results) / count, 2),
        )

    @staticmethod
    def _default_ranker(case: RetrievalBenchmarkCase, tenant_id: str, top_k: int) -> list[str]:
        if case.expected_report is None:
            result = group_retriever.search_groups(tenant_id, case.question, n_results=top_k)
            return [str(item["group_id"]) for item in result.get("top_candidates", [])]
        result = report_retriever.search_reports(
            tenant_id, case.question, n_results=top_k, group_filter=case.expected_group
        )
        return [str(item["report_id"]) for item in result.get("top_candidates", [])]

    def run(
        self,
        tenant_id: str,
        top_k: int = 3,
        minimum_top1: float = 0.80,
        dataset_path: Path | None = None,
        ranker: Ranker | None = None,
    ) -> RetrievalBenchmarkResult:
        rank_candidates = ranker or self._default_ranker
        results: list[RetrievalCaseResult] = []
        cases = self.load_cases(dataset_path)
        for case in cases:
            levels = [("group", case.expected_group)]
            if case.expected_report:
                levels.append(("report", case.expected_report))
            for level, expected in levels:
                benchmark_case = case if level == "report" else case.model_copy(update={"expected_report": None})
                started = perf_counter()
                error = None
                try:
                    ranked_ids = rank_candidates(benchmark_case, tenant_id, top_k)[:top_k]
                except Exception as exc:
                    ranked_ids, error = [], str(exc)
                latency = (perf_counter() - started) * 1000
                rank = self._rank(expected, ranked_ids)
                results.append(RetrievalCaseResult(
                    id=case.id, question=case.question, level=level, expected=expected,
                    ranked_ids=ranked_ids, rank=rank, passed_top1=rank == 1,
                    passed_top_k=rank is not None and rank <= top_k,
                    latency_ms=round(latency, 2), error=error,
                ))
        group_results = [item for item in results if item.level == "group"]
        report_results = [item for item in results if item.level == "report"]
        group_metrics, report_metrics = self._metrics(group_results), self._metrics(report_results)
        overall_count = len(results)
        overall = round(sum(item.passed_top1 for item in results) / overall_count, 4) if overall_count else 0.0
        return RetrievalBenchmarkResult(
            status="passed" if overall >= minimum_top1 else "failed",
            tenant_id=tenant_id, top_k=top_k, minimum_top1=minimum_top1,
            group=group_metrics, report=report_metrics,
            overall_top1_accuracy=overall, cases=results,
        )


retrieval_benchmark_service = RetrievalBenchmarkService()
