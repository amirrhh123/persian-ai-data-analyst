from backend.answer.formatter import result_formatter
from backend.answer.models import AnswerRequest, AnswerResponse
from backend.answer.prompt_builder import answer_prompt_builder
from backend.services.llm_service import llm_service


class AnswerGenerator:
    def __init__(self):
        self.llm = llm_service
        self.formatter = result_formatter
        self.prompt_builder = answer_prompt_builder

    async def generate(self, request: AnswerRequest) -> AnswerResponse:
        formatted = self.formatter.format_result(request.result, request.report_name)
        deterministic = self._deterministic_answer(request.result)
        if deterministic is not None:
            return AnswerResponse(
                answer=deterministic,
                formatted_data=formatted.model_dump(),
                confidence=1.0,
            )

        prompt = self.prompt_builder.build_prompt(request, formatted)
        system_prompt = (
            "فقط بر اساس ستون‌ها و ردیف‌های نتیجه پاسخ بده. "
            "نام، تاریخ، شغل، وضعیت یا عددی را که در نتیجه وجود ندارد اضافه نکن."
        )

        try:
            response = await self.llm.chat(prompt, system_prompt)
            return AnswerResponse(
                answer=response,
                formatted_data=formatted.model_dump(),
                confidence=0.9,
            )
        except Exception as exc:
            return AnswerResponse(
                answer=f"خطا در تولید پاسخ: {exc}",
                formatted_data=formatted.model_dump(),
                confidence=0.0,
            )

    def _deterministic_answer(self, result):
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        if not rows:
            return "داده‌ای مطابق پرسش پیدا نشد."

        def format_row(row):
            return "، ".join(f"{column}: {row.get(column)}" for column in columns)

        if len(rows) == 1:
            return format_row(rows[0])

        if len(rows) <= 10:
            return "\n".join(f"{index + 1}. {format_row(row)}" for index, row in enumerate(rows))

        return (
            f"تعداد ردیف‌ها: {result.get('row_count', len(rows))}. "
            "خروجی کامل در جدول پایین نمایش داده شده است."
        )


answer_generator = AnswerGenerator()
