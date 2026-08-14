import time
from typing import Dict, List, Optional, Any
from tests.benchmark.dataset import BenchmarkCase, BenchmarkDataset
from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever
from backend.sql.planner import sql_planner
from backend.sql.validator import sql_validator
from backend.database.sync_service import schema_sync_service
from backend.config import get_settings


class BenchmarkResult:
    def __init__(self, case: BenchmarkCase):
        self.case = case
        self.group_match = False
        self.report_match = False
        self.tables_match = False
        self.sql_valid = False
        self.execution_ready = False
        
        self.retrieval_time = 0.0
        self.planning_time = 0.0
        self.validation_time = 0.0
        self.total_time = 0.0
        
        self.predicted_group = ""
        self.predicted_group_name = ""
        self.predicted_group_confidence = 0.0
        self.predicted_report = ""
        self.predicted_report_name = ""
        self.predicted_tables = []
        self.errors = []
    
    def to_dict(self) -> Dict:
        return {
            "id": self.case.id,
            "question": self.case.question,
            "category": self.case.category,
            "expected_group": self.case.expected_group,
            "predicted_group": self.predicted_group,
            "predicted_group_name": self.predicted_group_name,
            "predicted_group_confidence": self.predicted_group_confidence,
            "group_match": self.group_match,
            "expected_report": self.case.expected_report,
            "predicted_report": self.predicted_report,
            "predicted_report_name": self.predicted_report_name,
            "report_match": self.report_match,
            "expected_tables": self.case.expected_tables,
            "predicted_tables": self.predicted_tables,
            "tables_match": self.tables_match,
            "sql_valid": self.sql_valid,
            "execution_ready": self.execution_ready,
            "retrieval_time": round(self.retrieval_time, 3),
            "planning_time": round(self.planning_time, 3),
            "total_time": round(self.total_time, 3),
            "errors": self.errors
        }
    
    def print_detail(self) -> None:
        status = "✓" if self.execution_ready else "✗"
        print(f"\n{status} [{self.case.id}] {self.case.question[:60]}...")
        print(f"  Category: {self.case.category}")
        print(f"  Group:    expected='{self.case.expected_group}' → actual='{self.predicted_group}' {'✓' if self.group_match else '✗'}")
        print(f"  Report:   expected='{self.case.expected_report}' → actual='{self.predicted_report}' {'✓' if self.report_match else '✗'}")
        print(f"  Tables:   expected={self.case.expected_tables} → actual={self.predicted_tables} {'✓' if self.tables_match else '✗'}")
        print(f"  Time:     {self.total_time*1000:.1f}ms")
        if self.errors:
            print(f"  Errors:   {self.errors}")


class BenchmarkEvaluator:
    def __init__(self, tenant_id: str = None):
        self.settings = get_settings()
        self.tenant_id = tenant_id or self.settings.tenant_id
        self._synced = False
        self._group_count = 0
        self._report_count = 0
    
    def _ensure_synced(self):
        if not self._synced:
            try:
                from backend.reports.group_retriever import group_retriever
                from backend.reports.retriever import report_retriever
                self._group_count = group_retriever.sync_groups(self.tenant_id)
                self._report_count = report_retriever.sync_reports(self.tenant_id)
                self._synced = True
                print(f"  Synced: {self._group_count} groups, {self._report_count} reports")
            except Exception as e:
                print(f"  Sync error: {e}")
    
    def evaluate_group(self, result: BenchmarkResult, question: str) -> None:
        start = time.time()
        
        try:
            group_result = group_retriever.search_groups(self.tenant_id, question)
            result.predicted_group = group_result.get("group_id", "")
            result.predicted_group_name = group_result.get("group_name", "")
            result.predicted_group_confidence = group_result.get("confidence", 0.0)
            result.group_match = result.predicted_group == result.case.expected_group
        except Exception as e:
            result.errors.append(f"Group retrieval error: {str(e)}")
        
        result.retrieval_time += time.time() - start
    
    def evaluate_report(self, result: BenchmarkResult, question: str) -> None:
        start = time.time()
        
        try:
            report_result = report_retriever.search_reports(
                self.tenant_id, question, group_filter=result.predicted_group
            )
            result.predicted_report = report_result.get("report_id", "")
            result.predicted_report_name = report_result.get("report_name", "")
            result.report_match = result.predicted_report == result.case.expected_report
        except Exception as e:
            result.errors.append(f"Report retrieval error: {str(e)}")
        
        result.retrieval_time += time.time() - start
    
    def evaluate_plan(self, result: BenchmarkResult, question: str) -> None:
        start = time.time()
        
        try:
            schema = schema_sync_service.load_schema(self.tenant_id)
            plan = sql_planner.create_plan(question, schema)
            result.predicted_tables = plan.required_tables
            
            expected = set(result.case.expected_tables)
            predicted = set(result.predicted_tables)
            result.tables_match = expected.issubset(predicted) or predicted.issubset(expected)
        except Exception as e:
            result.errors.append(f"Planning error: {str(e)}")
        
        result.planning_time = time.time() - start
    
    def evaluate_validation(self, result: BenchmarkResult) -> None:
        start = time.time()
        
        try:
            schema = schema_sync_service.load_schema(self.tenant_id)
            
            if not schema.tables:
                result.sql_valid = True
                result.execution_ready = len(result.predicted_tables) > 0
                result.validation_time = time.time() - start
                return
            
            mock_sql = f"SELECT * FROM {result.predicted_tables[0]}" if result.predicted_tables else "SELECT 1"
            validation = sql_validator.validate(mock_sql, schema)
            result.sql_valid = validation.is_valid
            result.execution_ready = validation.is_valid and len(result.predicted_tables) > 0
        except Exception as e:
            result.errors.append(f"Validation error: {str(e)}")
        
        result.validation_time = time.time() - start
    
    def evaluate_case(self, case: BenchmarkCase) -> BenchmarkResult:
        result = BenchmarkResult(case)
        total_start = time.time()
        
        self._ensure_synced()
        
        self.evaluate_group(result, case.question)
        self.evaluate_report(result, case.question)
        self.evaluate_plan(result, case.question)
        self.evaluate_validation(result)
        
        result.total_time = time.time() - total_start
        return result
    
    def evaluate_dataset(self, dataset: BenchmarkDataset) -> List[BenchmarkResult]:
        results = []
        for i, case in enumerate(dataset.get_cases()):
            print(f"\n[{i+1}/{dataset.get_count()}] Evaluating: {case.question[:50]}...")
            result = self.evaluate_case(case)
            results.append(result)
        return results


class BenchmarkReport:
    def __init__(self, results: List[BenchmarkResult]):
        self.results = results
    
    def get_summary(self) -> Dict:
        total = len(self.results)
        group_correct = sum(1 for r in self.results if r.group_match)
        report_correct = sum(1 for r in self.results if r.report_match)
        tables_correct = sum(1 for r in self.results if r.tables_match)
        sql_valid = sum(1 for r in self.results if r.sql_valid)
        execution_ready = sum(1 for r in self.results if r.execution_ready)
        
        avg_retrieval_time = sum(r.retrieval_time for r in self.results) / total if total > 0 else 0
        avg_planning_time = sum(r.planning_time for r in self.results) / total if total > 0 else 0
        avg_total_time = sum(r.total_time for r in self.results) / total if total > 0 else 0
        
        return {
            "total_cases": total,
            "group_accuracy": round(group_correct / total * 100, 2) if total > 0 else 0,
            "report_accuracy": round(report_correct / total * 100, 2) if total > 0 else 0,
            "tables_accuracy": round(tables_correct / total * 100, 2) if total > 0 else 0,
            "sql_validation_rate": round(sql_valid / total * 100, 2) if total > 0 else 0,
            "execution_readiness": round(execution_ready / total * 100, 2) if total > 0 else 0,
            "avg_retrieval_time_ms": round(avg_retrieval_time * 1000, 2),
            "avg_planning_time_ms": round(avg_planning_time * 1000, 2),
            "avg_total_time_ms": round(avg_total_time * 1000, 2),
            "errors_count": sum(1 for r in self.results if r.errors),
            "group_correct": group_correct,
            "report_correct": report_correct,
            "tables_correct": tables_correct
        }
    
    def get_by_category(self) -> Dict:
        categories = {}
        for r in self.results:
            cat = r.case.category
            if cat not in categories:
                categories[cat] = {"total": 0, "group_correct": 0, "report_correct": 0, "tables_correct": 0}
            categories[cat]["total"] += 1
            if r.group_match:
                categories[cat]["group_correct"] += 1
            if r.report_match:
                categories[cat]["report_correct"] += 1
            if r.tables_match:
                categories[cat]["tables_correct"] += 1
        
        for cat, data in categories.items():
            total = data["total"]
            data["group_accuracy"] = round(data["group_correct"] / total * 100, 2) if total > 0 else 0
            data["report_accuracy"] = round(data["report_correct"] / total * 100, 2) if total > 0 else 0
            data["tables_accuracy"] = round(data["tables_correct"] / total * 100, 2) if total > 0 else 0
        
        return categories
    
    def get_failed_cases(self) -> List[Dict]:
        return [r.to_dict() for r in self.results if not r.execution_ready]
    
    def print_report(self) -> None:
        summary = self.get_summary()
        by_category = self.get_by_category()
        
        print("\n" + "=" * 70)
        print("BENCHMARK REPORT")
        print("=" * 70)
        
        print(f"\nTotal Cases: {summary['total_cases']}")
        print(f"Group Correct: {summary['group_correct']}/{summary['total_cases']}")
        print(f"Report Correct: {summary['report_correct']}/{summary['total_cases']}")
        print(f"Tables Correct: {summary['tables_correct']}/{summary['total_cases']}")
        
        print(f"\nAccuracy Metrics:")
        print(f"  Group Accuracy:      {summary['group_accuracy']}%")
        print(f"  Report Accuracy:     {summary['report_accuracy']}%")
        print(f"  Tables Accuracy:     {summary['tables_accuracy']}%")
        print(f"  SQL Validation Rate: {summary['sql_validation_rate']}%")
        print(f"  Execution Readiness: {summary['execution_readiness']}%")
        
        print(f"\nPerformance Metrics:")
        print(f"  Avg Retrieval Time:  {summary['avg_retrieval_time_ms']}ms")
        print(f"  Avg Planning Time:   {summary['avg_planning_time_ms']}ms")
        print(f"  Avg Total Time:      {summary['avg_total_time_ms']}ms")
        print(f"  Errors:              {summary['errors_count']}")
        
        print(f"\nBy Category:")
        for cat, data in by_category.items():
            print(f"\n  {cat.upper()}:")
            print(f"    Group Accuracy:    {data['group_accuracy']}% ({data['group_correct']}/{data['total']})")
            print(f"    Report Accuracy:   {data['report_accuracy']}% ({data['report_correct']}/{data['total']})")
            print(f"    Tables Accuracy:   {data['tables_accuracy']}% ({data['tables_correct']}/{data['total']})")
        
        print(f"\nDetailed Results:")
        for r in self.results:
            r.print_detail()
        
        print("\n" + "=" * 70)
