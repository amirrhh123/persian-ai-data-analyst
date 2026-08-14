from typing import Dict, Any, List
from backend.answer.models import AnswerRequest, FormattedResult


class AnswerPromptBuilder:
    def build_prompt(
        self,
        request: AnswerRequest,
        formatted: FormattedResult
    ) -> str:
        context_parts = []
        
        if request.group_name:
            context_parts.append(f"زمینه: {request.group_name}")
        if request.report_name:
            context_parts.append(f"گزارش: {request.report_name}")
        
        context = "\n".join(context_parts) if context_parts else "بدون زمینه خاص"
        
        data_text = self._format_data_for_prompt(request.result)
        
        prompt = f"""سوال کاربر: {request.question}

زمینه:
{context}

داده‌های استخراج شده:
{data_text}

پاسخ خود را بر اساس فقط داده‌های بالا بنویس. اطلاعاتی اضافه نکن.
پاسخ را به فارسی و مختصر بنویس.
"""
        
        return prompt
    
    def _format_data_for_prompt(self, result: Dict[str, Any]) -> str:
        if not result or not result.get("rows"):
            return "داده‌ای موجود نیست"
        
        rows = result.get("rows", [])
        columns = result.get("columns", [])
        
        lines = [f"ستون‌ها: {', '.join(columns)}"]
        lines.append(f"تعداد ردیف‌ها: {result.get('row_count', 0)}")
        
        for i, row in enumerate(rows[:5]):
            row_str = ", ".join([f"{col}: {row.get(col, '-')}" for col in columns])
            lines.append(f"ردیف {i+1}: {row_str}")
        
        if len(rows) > 5:
            lines.append(f"... و {len(rows) - 5} ردیف دیگر")
        
        return "\n".join(lines)


answer_prompt_builder = AnswerPromptBuilder()
