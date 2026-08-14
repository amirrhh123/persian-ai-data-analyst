from typing import List, Dict, Any
from backend.reports.retriever import report_retriever
from backend.reports.models import ReportSearchResult, ReportSyncResponse


class ReportService:
    def sync_reports(self, tenant_id: str) -> ReportSyncResponse:
        try:
            count = report_retriever.sync_reports(tenant_id)
            return ReportSyncResponse(
                tenant_id=tenant_id,
                reports_synced=count,
                status="success"
            )
        except Exception as e:
            return ReportSyncResponse(
                tenant_id=tenant_id,
                reports_synced=0,
                status=f"error: {str(e)}"
            )
    
    def search_reports(self, tenant_id: str, question: str) -> ReportSearchResult:
        try:
            result = report_retriever.search_reports(tenant_id, question)
            return ReportSearchResult(
                report_id=result["report_id"],
                confidence=result["confidence"],
                reason=result["reason"]
            )
        except Exception as e:
            return ReportSearchResult(
                report_id="",
                confidence=0.0,
                reason=f"خطا در جستجو: {str(e)}"
            )
    
    def get_report_count(self, tenant_id: str) -> int:
        return report_retriever.vector_store.get_collection_count(tenant_id)


report_service = ReportService()
