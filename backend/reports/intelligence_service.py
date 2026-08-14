from typing import Dict, Any
from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever
from backend.reports.group_models import TwoStageSearchResult, ReportGroupSyncResponse
from backend.reports.models import ReportSyncResponse
from backend.config import get_settings


class IntelligenceService:
    def __init__(self):
        self.settings = get_settings()
    
    def sync_groups(self, tenant_id: str) -> ReportGroupSyncResponse:
        try:
            count = group_retriever.sync_groups(tenant_id)
            return ReportGroupSyncResponse(
                tenant_id=tenant_id,
                groups_synced=count,
                status="success"
            )
        except Exception as e:
            return ReportGroupSyncResponse(
                tenant_id=tenant_id,
                groups_synced=0,
                status=f"error: {str(e)}"
            )
    
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
    
    def search_two_stage(
        self,
        tenant_id: str,
        question: str
    ) -> TwoStageSearchResult:
        group_result = group_retriever.search_groups(tenant_id, question)
        
        if not group_result["group_id"]:
            return TwoStageSearchResult(
                group_id="",
                group_name="",
                report_id="",
                report_name="",
                confidence=0.0,
                reason="هیچ گروهی یافت نشد"
            )
        
        report_result = report_retriever.search_reports(
            tenant_id,
            question,
            group_filter=group_result["group_id"]
        )
        
        overall_confidence = (group_result["confidence"] + report_result["confidence"]) / 2
        
        return TwoStageSearchResult(
            group_id=group_result["group_id"],
            group_name=group_result["group_name"],
            report_id=report_result["report_id"],
            report_name=report_result.get("report_name", ""),
            confidence=round(overall_confidence, 2),
            reason=f"گروه '{group_result['group_name']}' و گزارش '{report_result.get('report_name', '')}' یافت شد"
        )


intelligence_service = IntelligenceService()
