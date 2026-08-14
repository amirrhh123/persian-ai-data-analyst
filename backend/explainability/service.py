import json
import re
from typing import Any, Optional

from backend.pipeline.intent import QueryIntent
from backend.sql.models import SQLPlan, ValidationResult


class ExplainabilityService:
    def build(
        self,
        *,
        question: str,
        plan: Optional[SQLPlan],
        sql: str | None,
        validation: Optional[ValidationResult],
        intent: Optional[QueryIntent] = None,
        result: Optional[dict[str, Any]] = None,
        generator_explanation: str | None = None,
    ) -> str:
        payload = {
            "summary": self._summary(plan, validation, result),
            "table_selection": self._table_selection(plan),
            "joins": self._joins(plan),
            "filters": self._filters(plan, intent),
            "aggregation": self._aggregation(plan, intent),
            "safety": self._safety(sql, validation),
            "result": self._result(result),
            "generator_explanation": generator_explanation or "",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _summary(self, plan: Optional[SQLPlan], validation: Optional[ValidationResult], result: Optional[dict[str, Any]]) -> str:
        tables = ", ".join(plan.required_tables) if plan and plan.required_tables else "نامشخص"
        valid_text = "معتبر" if validation and validation.is_valid else "نامعتبر یا بررسی‌نشده"
        row_count = result.get("row_count") if result else None
        row_text = f" و {row_count} ردیف نتیجه برگشت" if row_count is not None else ""
        return f"سیستم جدول‌های {tables} را انتخاب کرد، SQL را {valid_text} تشخیص داد{row_text}."

    def _table_selection(self, plan: Optional[SQLPlan]) -> dict[str, Any]:
        if not plan:
            return {"tables": [], "reason": "پلن SQL در دسترس نیست."}
        return {
            "tables": plan.required_tables,
            "selected_columns": plan.selected_columns,
            "reason": "جدول‌ها براساس موجودیت و فیلترهای استخراج‌شده از سؤال انتخاب شدند.",
        }

    def _joins(self, plan: Optional[SQLPlan]) -> list[dict[str, Any]]:
        if not plan:
            return []
        return [
            {
                "from": f"{join.get('from_table')}.{join.get('from_column')}",
                "to": f"{join.get('to_table')}.{join.get('to_column')}",
                "reason": "برای اتصال موجودیت‌های مرتبط در schema استفاده شد.",
            }
            for join in plan.joins
        ]

    def _filters(self, plan: Optional[SQLPlan], intent: Optional[QueryIntent]) -> list[dict[str, Any]]:
        filters = []
        if plan:
            filters.extend(
                {
                    "column": item.get("column"),
                    "operator": item.get("operator"),
                    "value": self._redact_value(item.get("column", ""), item.get("value")),
                }
                for item in plan.filters
            )
        if intent and intent.province:
            filters.append({"column": "province", "operator": "=", "value": intent.province})
        return filters

    def _aggregation(self, plan: Optional[SQLPlan], intent: Optional[QueryIntent]) -> dict[str, Any]:
        return {
            "intent_aggregation": intent.aggregation if intent else None,
            "plan_aggregations": plan.aggregations if plan else [],
            "group_by": plan.group_by if plan else [],
            "order_by": plan.order_by if plan else None,
            "limit": plan.limit if plan else None,
        }

    def _safety(self, sql: str | None, validation: Optional[ValidationResult]) -> dict[str, Any]:
        normalized = (sql or "").lower()
        return {
            "select_only": bool(re.match(r"^\s*select\b", normalized)),
            "has_forbidden_write": bool(re.search(r"\b(insert|update|delete|drop)\b", normalized)),
            "validated": bool(validation and validation.is_valid),
            "errors": validation.errors if validation else [],
            "warnings": validation.warnings if validation else [],
        }

    def _result(self, result: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not result:
            return {"executed": False}
        return {
            "executed": True,
            "row_count": result.get("row_count", 0),
            "columns": result.get("columns", []),
            "data_policy": result.get("data_policy"),
        }

    def _redact_value(self, column: str, value: Any) -> Any:
        if value is None:
            return None
        if "national_id" in column.lower() or re.fullmatch(r"\d{10}", str(value)):
            return "***"
        return value


explainability_service = ExplainabilityService()
