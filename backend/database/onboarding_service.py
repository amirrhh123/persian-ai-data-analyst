import json
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.database.models import DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot


SENSITIVE_NAME_PATTERNS = {
    "national_id": "کد ملی",
    "ssn": "شناسه ملی/SSN",
    "phone": "شماره تلفن",
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

TEXT_TYPES = {"character varying", "character", "text", "USER-DEFINED"}
NUMERIC_TYPES = {"integer", "bigint", "numeric", "double precision", "real", "decimal"}


class DatabaseOnboardingService:
    def __init__(self):
        self.settings = get_settings()
        self.schema_root = Path(__file__).parent.parent.parent / "schema" / "tenants"

    def load_snapshot(self, tenant_id: str | None = None) -> SchemaDiscoverySnapshot | None:
        tenant = tenant_id or self.settings.tenant_id
        path = self.schema_root / tenant / "discovery.json"
        if not path.exists():
            return None
        return SchemaDiscoverySnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def build_report(self, snapshot: SchemaDiscoverySnapshot | None) -> dict[str, Any]:
        if snapshot is None:
            return {
                "status": "blocked",
                "message": "ابتدا باید schema discovery اجرا شود.",
                "summary": {
                    "tables": 0,
                    "columns": 0,
                    "relationships": 0,
                    "total_rows": 0,
                    "sensitive_columns": 0,
                    "warnings": 0,
                    "blockers": 1,
                },
                "checks": [
                    {
                        "id": "discovery_snapshot",
                        "status": "blocked",
                        "message": "فایل schema discovery پیدا نشد.",
                    }
                ],
                "tables": [],
                "recommended_actions": ["POST /database/discovery/sync را اجرا کنید."],
            }

        checks: list[dict[str, Any]] = []
        table_reports = [self._table_report(table) for table in snapshot.tables]
        sensitive_columns = [
            item
            for table in table_reports
            for item in table["sensitive_columns"]
        ]

        checks.append(self._check(snapshot.tables, "tables_present", "blocked", "هیچ جدولی در schema پیدا نشد."))
        checks.extend(self._relationship_checks(snapshot))
        checks.extend(self._table_checks(table_reports))
        checks.extend(self._sample_value_checks(snapshot.tables))

        blockers = sum(1 for check in checks if check["status"] == "blocked")
        warnings = sum(1 for check in checks if check["status"] == "warning")
        status = "blocked" if blockers else "warning" if warnings else "ok"

        return {
            "status": status,
            "message": self._status_message(status),
            "tenant_id": snapshot.tenant_id,
            "database_name": snapshot.database_name,
            "schema_name": snapshot.schema_name,
            "fingerprint": snapshot.fingerprint,
            "generated_at": snapshot.generated_at,
            "summary": {
                "tables": len(snapshot.tables),
                "columns": sum(len(table.columns) for table in snapshot.tables),
                "relationships": len(snapshot.relationships),
                "total_rows": sum(table.row_count for table in snapshot.tables),
                "sensitive_columns": len(sensitive_columns),
                "warnings": warnings,
                "blockers": blockers,
            },
            "checks": checks,
            "tables": table_reports,
            "recommended_actions": self._recommended_actions(checks),
        }

    def quality_gate(self, snapshot: SchemaDiscoverySnapshot | None) -> dict[str, Any]:
        report = self.build_report(snapshot)
        blockers = [
            check
            for check in report["checks"]
            if check["status"] == "blocked"
        ]
        warnings = [
            check
            for check in report["checks"]
            if check["status"] == "warning"
        ]
        gate_status = "blocked" if blockers else "passed_with_warnings" if warnings else "passed"
        return {
            "status": gate_status,
            "message": self._gate_message(gate_status),
            "blockers": blockers,
            "warnings": warnings,
            "summary": report["summary"],
            "recommended_actions": report["recommended_actions"],
            "report": report,
        }

    def _table_report(self, table: DiscoveredTableInfo) -> dict[str, Any]:
        return {
            "name": table.name,
            "row_count": table.row_count,
            "columns": len(table.columns),
            "primary_keys": table.primary_keys,
            "foreign_keys": [fk.model_dump() for fk in table.foreign_keys],
            "indexes": len(table.indexes),
            "sensitive_columns": [
                {"column": column.name, "reason": reason}
                for column in table.columns
                for reason in [self._sensitive_reason(column)]
                if reason
            ],
            "text_columns_without_samples": [
                column.name
                for column in table.columns
                if self._needs_sample_values(column)
            ],
        }

    def _check(self, items: list[Any], check_id: str, empty_status: str, empty_message: str) -> dict[str, Any]:
        if items:
            return {"id": check_id, "status": "ok", "message": "آماده است."}
        return {"id": check_id, "status": empty_status, "message": empty_message}

    def _relationship_checks(self, snapshot: SchemaDiscoverySnapshot) -> list[dict[str, Any]]:
        if not snapshot.relationships and len(snapshot.tables) > 1:
            return [{
                "id": "relationships_present",
                "status": "warning",
                "message": "چند جدول وجود دارد اما رابطه foreign key کشف نشده است.",
            }]
        return [{"id": "relationships_present", "status": "ok", "message": "روابط schema کشف شده‌اند."}]

    def _table_checks(self, table_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checks = []
        without_pk = [table["name"] for table in table_reports if not table["primary_keys"]]
        huge_without_index = [
            table["name"]
            for table in table_reports
            if table["row_count"] >= 100_000 and table["indexes"] == 0
        ]
        if without_pk:
            checks.append({
                "id": "primary_keys",
                "status": "warning",
                "message": "برخی جدول‌ها primary key ندارند.",
                "tables": without_pk,
            })
        else:
            checks.append({"id": "primary_keys", "status": "ok", "message": "همه جدول‌ها primary key دارند."})

        if huge_without_index:
            checks.append({
                "id": "large_tables_indexed",
                "status": "warning",
                "message": "برخی جدول‌های بزرگ index ثبت‌شده ندارند.",
                "tables": huge_without_index,
            })
        else:
            checks.append({"id": "large_tables_indexed", "status": "ok", "message": "جدول بزرگ بدون index دیده نشد."})
        return checks

    def _sample_value_checks(self, tables: list[DiscoveredTableInfo]) -> list[dict[str, Any]]:
        missing = {
            table.name: [
                column.name
                for column in table.columns
                if self._needs_sample_values(column)
            ]
            for table in tables
        }
        missing = {table: columns for table, columns in missing.items() if columns}
        if missing:
            return [{
                "id": "sample_values",
                "status": "warning",
                "message": "برخی ستون‌های متنی sample value ندارند؛ تشخیص معنایی سخت‌تر می‌شود.",
                "columns": missing,
            }]
        return [{"id": "sample_values", "status": "ok", "message": "sample valueهای لازم موجود هستند."}]

    def _needs_sample_values(self, column: DiscoveredColumnInfo) -> bool:
        return (
            column.data_type in TEXT_TYPES
            and not column.is_primary_key
            and not column.name.endswith("_id")
            and not column.sample_values
        )

    def _sensitive_reason(self, column: DiscoveredColumnInfo) -> str | None:
        name = column.name.lower()
        for pattern, reason in SENSITIVE_NAME_PATTERNS.items():
            if pattern in name:
                return reason
        return None

    def _status_message(self, status: str) -> str:
        return {
            "ok": "دیتابیس برای ساخت semantic layer آماده است.",
            "warning": "دیتابیس قابل استفاده است اما چند هشدار برای بررسی دارد.",
            "blocked": "دیتابیس هنوز آماده onboarding نیست.",
        }[status]

    def _recommended_actions(self, checks: list[dict[str, Any]]) -> list[str]:
        actions = []
        for check in checks:
            if check["status"] == "ok":
                continue
            if check["id"] == "relationships_present":
                actions.append("foreign keyها یا joinهای semantic را برای جدول‌های مرتبط مشخص کنید.")
            elif check["id"] == "primary_keys":
                actions.append("برای جدول‌های بدون primary key، کلید اصلی یا ستون unique معرفی کنید.")
            elif check["id"] == "sample_values":
                actions.append("schema discovery را با sample_value_limit مناسب اجرا کنید.")
            elif check["id"] == "large_tables_indexed":
                actions.append("برای جدول‌های بزرگ، indexهای مورد نیاز فیلتر و join را بررسی کنید.")
            else:
                actions.append(check["message"])
        return actions

    def _gate_message(self, status: str) -> str:
        return {
            "passed": "Schema quality gate passed.",
            "passed_with_warnings": "Schema quality gate passed with warnings.",
            "blocked": "Schema quality gate blocked semantic activation.",
        }[status]


database_onboarding_service = DatabaseOnboardingService()
