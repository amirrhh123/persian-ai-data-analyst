from typing import Optional

from backend.config import get_settings
from backend.semantic.models import (
    LightweightGapApplyResponse,
    LightweightGapApplyResult,
    LightweightGapSuggestion,
    LightweightGapSuggestionResponse,
    SemanticReviewRequest,
    SemanticSmokeTestResult,
)
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.review_service import semantic_review_service
from backend.semantic.smoke_test_runner import semantic_smoke_test_runner


class LightweightGapService:
    def __init__(self):
        self.settings = get_settings()

    async def suggest(
        self,
        tenant_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> LightweightGapSuggestionResponse:
        tenant = tenant_id or self.settings.tenant_id
        readiness = await semantic_smoke_test_runner.run(
            tenant_id=tenant,
            limit=limit,
            execute=False,
            save=False,
        )
        gaps = [result for result in readiness.results if self._is_lightweight_gap(result)]
        return LightweightGapSuggestionResponse(
            status="ready" if not gaps else "needs_semantic_work",
            tenant_id=tenant,
            total_cases=readiness.summary.total,
            lightweight_ready_rate=readiness.summary.lightweight_ready_rate,
            gap_count=len(gaps),
            suggestions=[self._suggest_for_gap(result) for result in gaps],
        )

    async def apply_suggestions(
        self,
        tenant_id: Optional[str] = None,
        limit: Optional[int] = None,
        validate_after: bool = True,
    ) -> LightweightGapApplyResponse:
        tenant = tenant_id or self.settings.tenant_id
        suggestions = await self.suggest(tenant_id=tenant, limit=limit)
        results: list[LightweightGapApplyResult] = []

        for suggestion in suggestions.suggestions:
            payload = dict(suggestion.suggested_review_payload)
            payload.pop("note", None)
            try:
                review = SemanticReviewRequest.model_validate(payload)
                response = semantic_review_service.apply_review(review, tenant)
                results.append(
                    LightweightGapApplyResult(
                        table=review.table,
                        column=review.column,
                        status=response.status,
                        message=response.message,
                        payload=payload,
                    )
                )
            except Exception as exc:
                results.append(
                    LightweightGapApplyResult(
                        table=str(payload.get("table") or suggestion.table),
                        column=payload.get("column"),
                        status="failed",
                        message=str(exc),
                        payload=payload,
                    )
                )

        applied = sum(1 for result in results if result.status == "success")
        failed = len(results) - applied
        validation = None
        validation_errors = 0
        validation_warnings = 0
        validation_issues: list[dict] = []
        if validate_after and applied:
            validation = semantic_activation_service.validate_current(tenant)
            validation_errors = sum(1 for issue in validation.issues if issue.severity == "error")
            validation_warnings = sum(1 for issue in validation.issues if issue.severity == "warning")
            validation_issues = [issue.model_dump(mode="json") for issue in validation.issues[:10]]

        if failed:
            status = "partial"
            next_action = "ناموفق‌ها را بررسی کنید، سپس دوباره پیشنهادها را اعمال کنید."
        elif validation and validation_errors:
            status = "applied_validation_failed"
            next_action = "خطاهای validation را رفع کنید؛ semantic هنوز نباید فعال شود."
        elif applied:
            status = "applied_validated" if validation else "success"
            next_action = "اکنون می‌توانید به‌روزرسانی کامل سیستم یا semantic activation را اجرا کنید."
        else:
            status = "success"
            next_action = "gap قابل اعمالی وجود نداشت."

        return LightweightGapApplyResponse(
            status=status,
            tenant_id=tenant,
            requested=len(results),
            applied=applied,
            failed=failed,
            results=results,
            validation_status=validation.status if validation else None,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            validation_issues=validation_issues,
            next_action=next_action,
            message=(
                "Review suggestions were applied and validation was checked."
                if applied
                else "No lightweight gap suggestions were applied."
            ),
        )

    def _is_lightweight_gap(self, result: SemanticSmokeTestResult) -> bool:
        return (
            result.error_code == "sql.llm_disabled"
            or result.response.get("generation_source") == "llm_disabled"
        )

    def _suggest_for_gap(self, result: SemanticSmokeTestResult) -> LightweightGapSuggestion:
        if result.kind == "count":
            action = "برای سؤال‌های شمارشی این جدول یک template قطعی COUNT اضافه شود."
            technical = f"Add deterministic COUNT template coverage for table '{result.table}'."
        elif result.kind == "list":
            action = "برای نمایش لیست اطلاعات این جدول، ستون‌های پیش‌فرض نمایش و template لیست تکمیل شود."
            technical = f"Review default_display_columns/profile_columns and list template for '{result.table}'."
        elif result.kind == "sample_filter":
            action = "برای فیلتر روی مقدار نمونه، alias ستون یا value mapping در پنل ادمین ثبت شود."
            technical = f"Add/approve semantic aliases or value mappings for sample filters on '{result.table}'."
        elif result.kind == "group_by":
            action = "برای گزارش‌های تفکیکی این جدول، template گروه‌بندی و alias ستون تفکیک تکمیل شود."
            technical = f"Add GROUP BY template coverage for '{result.table}'."
        elif result.kind in {"max", "min", "recent"}:
            action = "برای بیشترین/کمترین یا جدیدترین رکورد، ستون معیار و template رتبه‌بندی/مرتب‌سازی تکمیل شود."
            technical = f"Add ranking/sorting template coverage for kind '{result.kind}' on '{result.table}'."
        else:
            action = "معنی جدول و ستون‌های سؤال در semantic review بررسی و برای این نوع سؤال template اضافه شود."
            technical = f"Inspect semantic coverage for kind '{result.kind}' on '{result.table}'."

        return LightweightGapSuggestion(
            question=result.question,
            table=result.table,
            kind=result.kind,
            error_code=result.error_code,
            recommended_action=action,
            admin_hint=(
                "در پنل ادمین ابتدا «اصلاح معنی توسط انسان» را برای جدول/ستون مربوطه ثبت کنید، "
                "بعد «به‌روزرسانی کامل سیستم» و سپس «آمادگی حالت سبک» را دوباره اجرا کنید."
            ),
            technical_hint=technical,
            suggested_review_payload=self._review_payload(result),
        )

    def _review_payload(self, result: SemanticSmokeTestResult) -> dict:
        alias = self._suggested_alias(result)
        payload = {
            "target_type": "table",
            "table": result.table,
            "column": None,
            "aliases_fa": [alias] if alias else [result.table.replace("_", " ")],
            "display_name_fa": alias or result.table.replace("_", " "),
            "approved": True,
        }
        if result.kind in {"sample_filter", "group_by", "max", "min", "recent"}:
            payload["note"] = (
                "اگر مشکل مربوط به یک ستون خاص است، همین payload را در پنل ادمین با نام ستون همان فیلتر/تفکیک ثبت کنید."
            )
        return payload

    def _suggested_alias(self, result: SemanticSmokeTestResult) -> str:
        text = result.question.replace("جدول", " ").replace(result.table.replace("_", " "), " ")
        for marker in ["تعداد", "لیست", "اطلاعات", "به تفکیک", "بیشترین", "کمترین", "جدیدترین", "را", "بگو", "نشان بده"]:
            text = text.replace(marker, " ")
        alias = " ".join(part for part in text.split() if len(part.strip()) > 1).strip(" ؟?،,")
        return alias[:80]


lightweight_gap_service = LightweightGapService()
