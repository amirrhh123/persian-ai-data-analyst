from backend.pipeline.models import PipelineErrorDetail


class PipelineErrorTaxonomy:
    CODES = {
        "ambiguity.related_filter": "Related table/filter ambiguity.",
        "ambiguity.sample_value": "A sample value matched more than one semantic target.",
        "ambiguity.school_not_found": "Named school could not be resolved.",
        "ambiguity.school_multiple_matches": "Named school matched multiple rows.",
        "safety.rejected": "Question was rejected by safety policy.",
        "unsupported.out_of_scope": "Question is outside supported analytical scope.",
        "retrieval.group_error": "Group retrieval failed and fallback was used.",
        "retrieval.report_error": "Report retrieval failed and fallback was used.",
        "sql.planning_error": "SQL planning failed.",
        "sql.join_path_invalid": "SQL plan join path is missing, disconnected, or unsafe.",
        "sql.aggregate_safety_failed": "SQL plan aggregate shape does not match the normalized intent.",
        "sql.generation_failed": "SQL generation did not produce SQL.",
        "sql.llm_disabled": "LLM is disabled and no deterministic semantic/template route matched.",
        "sql.validation_failed": "Generated SQL failed validation.",
        "execution.failed": "SQL execution failed.",
        "result.shape_mismatch": "Executed SQL result shape does not match the normalized intent.",
        "routing.no_sql": "Pipeline could not route to SQL.",
        "expectation.mismatch": "Smoke/regression expectation did not match response.",
    }

    def catalog(self) -> dict:
        return {
            "status": "ok",
            "codes": [
                {
                    "code": code,
                    "description": description,
                    "user_message": self.user_message(code),
                }
                for code, description in sorted(self.CODES.items())
            ],
        }

    def detail(
        self,
        code: str,
        stage: str,
        message: str,
        severity: str = "error",
        user_message: str | None = None,
    ) -> PipelineErrorDetail:
        return PipelineErrorDetail(
            code=code,
            stage=stage,
            severity=severity,
            message=message,
            user_message=user_message or self.user_message(code),
        )

    def user_message(self, code: str) -> str:
        return {
            "ambiguity.related_filter": "سؤال چند معنی ممکن دارد؛ لطفاً منظور دقیق را مشخص کنید.",
            "ambiguity.sample_value": "یک مقدار در چند ستون پیدا شد؛ لطفاً ستون مورد نظر را مشخص کنید.",
            "ambiguity.school_not_found": "نام مدرسه در داده‌ها پیدا نشد.",
            "ambiguity.school_multiple_matches": "چند مدرسه مشابه پیدا شد؛ نام را دقیق‌تر وارد کنید.",
            "safety.rejected": "سؤال به دلیل سیاست ایمنی قابل اجرا نیست.",
            "unsupported.out_of_scope": "این نوع سؤال فعلاً در محدوده سیستم نیست.",
            "retrieval.group_error": "بازیابی گروه با خطا روبه‌رو شد و fallback استفاده شد.",
            "retrieval.report_error": "بازیابی گزارش با خطا روبه‌رو شد و fallback استفاده شد.",
            "sql.planning_error": "ساخت plan SQL با خطا روبه‌رو شد.",
            "sql.join_path_invalid": "مسیر اتصال جدول‌ها در SQL کامل یا امن نیست.",
            "sql.aggregate_safety_failed": "نوع خروجی SQL با منظور سؤال هماهنگ نیست.",
            "sql.generation_failed": "سیستم نتوانست SQL قابل اجرا بسازد.",
            "sql.llm_disabled": "حالت سبک فعال است؛ برای این سؤال الگوی قطعی پیدا نشد و مدل زبانی خاموش است.",
            "sql.validation_failed": "SQL تولیدشده از اعتبارسنجی عبور نکرد.",
            "execution.failed": "اجرای SQL روی دیتابیس ناموفق بود.",
        }.get(code, "خطای قابل دسته‌بندی رخ داد.")


pipeline_error_taxonomy = PipelineErrorTaxonomy()
