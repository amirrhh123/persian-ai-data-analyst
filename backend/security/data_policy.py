import re
from typing import Any, Optional

from backend.config import get_settings
from backend.semantic.activation_service import semantic_activation_service


SENSITIVE_PATTERNS = {
    "national_id": "شناسه ملی",
    "phone": "شماره تماس",
    "mobile": "شماره موبایل",
    "email": "ایمیل",
    "address": "آدرس",
    "salary": "حقوق",
    "wage": "حقوق",
    "iban": "شماره شبا",
    "card": "شماره کارت",
    "account": "حساب بانکی",
    "password": "رمز عبور",
}


class DataSensitivityPolicy:
    def __init__(self):
        self.settings = get_settings()

    def policy_report(self, tenant_id: Optional[str] = None) -> dict[str, Any]:
        tenant = tenant_id or self.settings.tenant_id
        columns = self.sensitive_columns(tenant)
        return {
            "tenant_id": tenant,
            "status": "ok",
            "default_action": "mask",
            "sensitive_columns": [
                {"table": table, "column": column, "reason": reason}
                for (table, column), reason in sorted(columns.items())
            ],
            "rules": [
                "Sensitive values are masked in pipeline results by default.",
                "National IDs keep only the last 4 digits.",
                "Phone-like values keep only the last 4 digits.",
                "Salary/payment columns are masked unless a future role-based permission allows them.",
            ],
        }

    def sensitive_columns(self, tenant_id: Optional[str] = None) -> dict[tuple[str, str], str]:
        tenant = tenant_id or self.settings.tenant_id
        sensitive: dict[tuple[str, str], str] = {}
        try:
            catalog = semantic_activation_service.load_active_catalog(tenant)
            for table in catalog.tables:
                for column in table.columns:
                    reason = self._reason(column.name, pii=column.pii)
                    if reason:
                        sensitive[(table.name, column.name)] = reason
        except Exception:
            pass
        return sensitive

    def apply_to_result(
        self,
        result: dict[str, Any],
        sql: str = "",
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not result:
            return result
        if not self.settings.data_masking_enabled:
            return result

        sensitive = self.sensitive_columns(tenant_id)
        sensitive_by_column = {column: reason for (_, column), reason in sensitive.items()}
        columns = list(result.get("columns") or [])
        masked_columns = [
            column
            for column in columns
            if self._is_sensitive_output_column(column, sensitive_by_column)
        ]
        if not masked_columns:
            return result

        rows = []
        for row in result.get("rows") or []:
            new_row = dict(row)
            for column in masked_columns:
                if column in new_row:
                    new_row[column] = self.mask_value(column, new_row[column])
            rows.append(new_row)

        protected = dict(result)
        protected["rows"] = rows
        protected["data_policy"] = {
            "masked_columns": masked_columns,
            "action": "mask",
        }
        return protected

    def mask_value(self, column: str, value: Any) -> Any:
        if value is None:
            return None
        text = str(value)
        if not text:
            return text
        normalized = column.lower()
        if "national_id" in normalized or re.fullmatch(r"\d{10}", text):
            return self._keep_last(text, 4)
        if any(token in normalized for token in ["phone", "mobile", "card", "iban", "account"]):
            return self._keep_last(text, 4)
        return "***"

    def _keep_last(self, text: str, count: int) -> str:
        if len(text) <= count:
            return "***"
        return f"***{text[-count:]}"

    def _is_sensitive_output_column(self, column: str, sensitive_by_column: dict[str, str]) -> bool:
        if column in sensitive_by_column:
            return True
        return self._reason(column) is not None

    def _reason(self, column: str, pii: bool = False) -> str | None:
        normalized = column.lower()
        for pattern, reason in SENSITIVE_PATTERNS.items():
            if pattern in normalized:
                return reason
        if pii:
            return "PII"
        return None


data_sensitivity_policy = DataSensitivityPolicy()
