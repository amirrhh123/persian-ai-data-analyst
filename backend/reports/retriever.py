from typing import List, Dict, Any, Optional
from backend.knowledge.loader import KnowledgeLoader
from backend.knowledge.models import Report, MetricDefinition, BusinessRule
from backend.reports.embedding import embedding_service
from backend.reports.hybrid_retrieval import HybridCandidate, hybrid_retriever
from backend.reports.reranker import retrieval_reranker
from backend.reports.confidence_gate import confidence_gate
from backend.reports.vector_store import vector_store
from pathlib import Path


class ReportRetriever:
    def __init__(self):
        self.tenants_dir = Path(__file__).parent.parent.parent / "knowledge" / "tenants"
    
    def _prepare_document(
        self,
        report: Report,
        metrics: List[MetricDefinition],
        rules: List[BusinessRule]
    ) -> str:
        parts = [
            f"نام گزارش: {report.name}",
            f"توضیحات: {report.description}",
            f"نمونه سوالات: {', '.join(report.example_questions)}"
        ]
        
        if report.group_id:
            parts.append(f"گروه: {report.group_id}")
        
        if metrics:
            metric_names = [m.name for m in metrics]
            parts.append(f"شاخص‌ها: {', '.join(metric_names)}")
        
        if rules:
            rule_names = [r.name for r in rules]
            parts.append(f"قوانین: {', '.join(rule_names)}")
        
        return "\n".join(parts)
    
    def _prepare_metadata(self, report: Report, tenant_id: str) -> Dict[str, Any]:
        return {
            "report_id": report.id,
            "tenant_id": tenant_id,
            "linked_table": report.linked_table,
            "report_name": report.name,
            "group_id": report.group_id or ""
        }
    
    def sync_reports(self, tenant_id: str) -> int:
        tenant_path = self.tenants_dir / tenant_id
        loader = KnowledgeLoader(tenant_path)
        
        reports = loader.load_all_reports()
        all_metrics = loader.load_metrics()
        all_rules = loader.load_rules()
        
        if not reports:
            return 0
        
        ids = []
        documents = []
        metadatas = []
        
        for report in reports:
            metrics = [m for m in all_metrics if m.id in report.allowed_metrics]
            rules = [r for r in all_rules if r.id in report.business_rules]
            
            document = self._prepare_document(report, metrics, rules)
            metadata = self._prepare_metadata(report, tenant_id)
            
            ids.append(f"{tenant_id}_{report.id}")
            documents.append(document)
            metadatas.append(metadata)
        
        embeddings = embedding_service.embed_batch(documents)
        
        vector_store.delete_collection(tenant_id)
        vector_store.add_documents(
            tenant_id=tenant_id,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        return len(reports)
    
    def search_reports(
        self,
        tenant_id: str,
        question: str,
        n_results: int = 1,
        group_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find the best report using dense and lexical evidence."""
        loader = KnowledgeLoader(self.tenants_dir / tenant_id)
        reports = loader.load_all_reports()
        if group_filter:
            reports = [report for report in reports if report.group_id == group_filter]
        if not reports:
            return self._empty_result()

        collection = vector_store.get_collection(tenant_id)
        where_filter = {"group_id": group_filter} if group_filter else None
        results = collection.query(
            query_embeddings=[embedding_service.embed_text(question)],
            n_results=len(reports),
            where=where_filter,
        )
        vector_scores: Dict[str, float] = {}
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        for index, metadata in enumerate(metadatas):
            report_id = metadata.get("report_id", "")
            distance = distances[index] if index < len(distances) else 1.0
            vector_scores[report_id] = max(0.0, min(1.0, 1.0 - distance))

        all_metrics = loader.load_metrics()
        all_rules = loader.load_rules()
        candidates: List[HybridCandidate] = []
        for report in reports:
            metrics = [metric for metric in all_metrics if metric.id in report.allowed_metrics]
            rules = [rule for rule in all_rules if rule.id in report.business_rules]
            candidates.append(
                HybridCandidate(
                    id=report.id,
                    document=self._prepare_document(report, metrics, rules),
                    metadata=self._prepare_metadata(report, tenant_id),
                )
            )

        hybrid_ranked = hybrid_retriever.rank(question, candidates, vector_scores)
        ranked = retrieval_reranker.rerank(question, hybrid_ranked)
        if not ranked:
            return self._empty_result()

        best = ranked[0]
        gate = confidence_gate.evaluate(ranked)
        report_name = str(best.source.candidate.metadata.get("report_name", ""))
        return {
            "report_id": best.source.candidate.id if gate.accepted else "",
            "report_name": report_name if gate.accepted else "",
            "suggested_report_id": best.source.candidate.id,
            "suggested_report_name": report_name,
            "confidence": round(best.final_score, 2),
            "reason": (
                f"گزارش '{report_name}' با بازیابی ترکیبی و اطمینان "
                f"{best.final_score:.2f} یافت شد"
            ),
            "retrieval_mode": "hybrid_reranked",
            "vector_score": best.source.vector_score,
            "lexical_score": best.source.lexical_score,
            "hybrid_score": best.source.final_score,
            "reranker_score": best.reranker_score,
            "confidence_gate": {
                "accepted": gate.accepted,
                "reason_code": gate.reason_code,
                "margin": gate.margin,
                "evidence_score": gate.evidence_score,
            },
            "top_candidates": [
                {
                    "report_id": item.source.candidate.id,
                    "report_name": item.source.candidate.metadata.get("report_name", ""),
                    "vector_score": item.source.vector_score,
                    "lexical_score": item.source.lexical_score,
                    "hybrid_score": item.source.final_score,
                    "reranker_score": item.reranker_score,
                    "final_score": item.final_score,
                    "rerank_features": {
                        "token_coverage": item.features.token_coverage,
                        "exact_phrase": item.features.exact_phrase,
                        "metadata_match": item.features.metadata_match,
                    },
                }
                for item in ranked[:n_results]
            ],
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        """Return a stable response when no report can be retrieved."""
        return {
            "report_id": "",
            "report_name": "",
            "suggested_report_id": "",
            "suggested_report_name": "",
            "confidence": 0.0,
            "reason": "هیچ گزارشی یافت نشد",
            "retrieval_mode": "hybrid_reranked",
            "vector_score": 0.0,
            "lexical_score": 0.0,
            "hybrid_score": 0.0,
            "reranker_score": 0.0,
            "confidence_gate": {
                "accepted": False,
                "reason_code": "no_candidates",
                "margin": 0.0,
                "evidence_score": 0.0,
            },
            "top_candidates": [],
        }

    def _search_reports_vector(
        self,
        tenant_id: str,
        question: str,
        n_results: int = 1,
        group_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        query_embedding = embedding_service.embed_text(question)
        
        collection = vector_store.get_collection(tenant_id)
        
        where_filter = None
        if group_filter:
            where_filter = {"group_id": group_filter}
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter
        )
        
        if not results["ids"] or not results["ids"][0]:
            return {
                "report_id": "",
                "report_name": "",
                "confidence": 0.0,
                "reason": "هیچ گزارشی یافت نشد"
            }
        
        report_id = results["metadatas"][0][0].get("report_id", "")
        report_name = results["metadatas"][0][0].get("report_name", "")
        distance = results["distances"][0][0] if results["distances"] else 1.0
        
        confidence = max(0.0, 1.0 - distance)
        reason = f"گزارش '{report_name}' با اطمینان {confidence:.2f} یافت شد"
        
        return {
            "report_id": report_id,
            "report_name": report_name,
            "confidence": round(confidence, 2),
            "reason": reason
        }


report_retriever = ReportRetriever()
