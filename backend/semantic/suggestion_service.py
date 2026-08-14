import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from backend.config import get_settings
from backend.database.models import (
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)
from backend.semantic.models import (
    SemanticBusinessTermSuggestion,
    SemanticCatalog,
    SemanticColumnSuggestion,
    SemanticJoinSuggestion,
    SemanticRuleSuggestion,
    SemanticSuggestionSet,
    SemanticTableSuggestion,
    SemanticValueMappingSuggestion,
    normalize_identifier,
)


KNOWN_TABLES: Dict[str, dict] = {
    "demo_training_requests": {
        "entity": "training_request",
        "display_name_fa": "درخواست‌های آموزشی",
        "description_fa": "درخواست‌های آموزشی، دوره‌ها و کارگاه‌های ثبت‌شده توسط مدارس، معلمان و واحدهای سازمانی.",
        "aliases_fa": [
            "درخواست آموزشی",
            "درخواست‌های آموزشی",
            "درخواست های آموزشی",
            "درخواست دوره",
            "درخواست‌های دوره",
            "دوره آموزشی",
            "دوره‌های آموزشی",
            "کارگاه آموزشی",
            "کارگاه هوش مصنوعی",
            "آموزش ضمن خدمت",
        ],
        "default_display_columns": [
            "requester_name",
            "request_type",
            "province",
            "priority",
            "status",
            "estimated_cost",
        ],
        "profile_columns": [
            "id",
            "requester_name",
            "requester_role",
            "request_type",
            "province",
            "city",
            "priority",
            "status",
            "assigned_unit",
            "estimated_cost",
            "requested_at",
            "created_at",
        ],
        "confidence": 0.95,
    },
    "employees": {
        "entity": "employee",
        "display_name_fa": "کارمندان",
        "description_fa": "اطلاعات پایه کارمندان و پرسنل سازمان.",
        "aliases_fa": ["کارمند", "کارمندان", "کارکنان", "پرسنل", "معلم", "دبیر"],
        "default_display_columns": ["first_name", "last_name", "position", "status"],
        "profile_columns": [
            "id",
            "national_id",
            "first_name",
            "last_name",
            "position",
            "status",
            "organization_unit_id",
            "hire_date",
            "created_at",
        ],
        "confidence": 0.95,
    },
    "students": {
        "entity": "student",
        "display_name_fa": "دانش‌آموزان",
        "description_fa": "اطلاعات پایه دانش‌آموزان ثبت‌شده در مدارس.",
        "aliases_fa": ["دانش‌آموز", "دانش آموز", "دانش‌آموزان", "محصل", "شاگرد"],
        "default_display_columns": ["first_name", "last_name", "grade", "status"],
        "profile_columns": [
            "id",
            "national_id",
            "first_name",
            "last_name",
            "grade",
            "status",
            "school_id",
            "enrollment_year",
            "created_at",
        ],
        "confidence": 0.95,
    },
    "schools": {
        "entity": "school",
        "display_name_fa": "مدارس",
        "description_fa": "اطلاعات مدارس، دبستان‌ها، دبیرستان‌ها و هنرستان‌ها.",
        "aliases_fa": ["مدرسه", "مدارس", "دبستان", "دبیرستان", "هنرستان", "آموزشگاه"],
        "default_display_columns": ["name", "school_type", "phone", "capacity"],
        "profile_columns": [
            "id",
            "name",
            "school_type",
            "phone",
            "address",
            "capacity",
            "established_year",
            "organization_unit_id",
        ],
        "confidence": 0.95,
    },
    "organization_units": {
        "entity": "organization_unit",
        "display_name_fa": "واحدهای سازمانی",
        "description_fa": "واحدهای سازمانی مانند اداره کل، استان و منطقه آموزشی.",
        "aliases_fa": ["واحد سازمانی", "اداره", "اداره کل", "استان", "شهر", "منطقه"],
        "default_display_columns": ["name", "unit_type", "province", "city"],
        "profile_columns": ["id", "name", "unit_type", "parent_id", "province", "city"],
        "confidence": 0.95,
    },
    "salary_items": {
        "entity": "salary",
        "display_name_fa": "آیتم‌های حقوقی",
        "description_fa": "اقلام حقوقی، پرداختی، مزایا، کسورات و حقوق خالص کارمندان.",
        "aliases_fa": ["حقوق", "پرداختی", "فیش حقوقی", "دستمزد", "مزایا", "کسورات"],
        "default_display_columns": ["employee_id", "year", "month", "base_salary", "net_salary"],
        "profile_columns": [
            "id",
            "employee_id",
            "year",
            "month",
            "base_salary",
            "allowances",
            "deductions",
            "net_salary",
            "payment_date",
        ],
        "confidence": 0.95,
    },
    "ranking_requests": {
        "entity": "ranking_request",
        "display_name_fa": "درخواست‌های رتبه‌بندی",
        "description_fa": "درخواست‌های رتبه‌بندی یا ارتقای کارمندان.",
        "aliases_fa": ["رتبه‌بندی", "رتبه بندی", "ارتقا", "درخواست رتبه"],
        "default_display_columns": ["employee_id", "ranking_type", "current_rank", "requested_rank", "status"],
        "profile_columns": [
            "id",
            "employee_id",
            "request_date",
            "ranking_type",
            "current_rank",
            "requested_rank",
            "status",
            "review_date",
        ],
        "confidence": 0.95,
    },
    "retirement_records": {
        "entity": "retirement_record",
        "display_name_fa": "سوابق بازنشستگی",
        "description_fa": "سوابق بازنشستگی، سنوات خدمت و مبلغ مستمری کارمندان.",
        "aliases_fa": ["بازنشستگی", "بازنشسته", "سوابق بازنشستگی", "مستمری"],
        "default_display_columns": ["employee_id", "retirement_date", "retirement_type", "years_of_service", "pension_amount"],
        "profile_columns": [
            "id",
            "employee_id",
            "retirement_date",
            "retirement_type",
            "years_of_service",
            "pension_amount",
            "reason",
        ],
        "confidence": 0.95,
    },
}


KNOWN_COLUMNS: Dict[str, dict] = {
    "id": {"display_name_fa": "شناسه", "aliases_fa": ["شناسه", "آیدی"], "description_fa": "شناسه داخلی رکورد."},
    "national_id": {
        "display_name_fa": "کد ملی",
        "aliases_fa": ["کد ملی", "شناسه ملی", "شماره ملی"],
        "description_fa": "شناسه ملی شخص؛ مقدار متنی است و باید در SQL داخل کوتیشن بیاید.",
        "value_type": "text_identifier",
        "pii": True,
        "confidence": 0.95,
    },
    "first_name": {"display_name_fa": "نام", "aliases_fa": ["نام", "اسم"], "description_fa": "نام کوچک شخص."},
    "last_name": {"display_name_fa": "نام خانوادگی", "aliases_fa": ["نام خانوادگی", "فامیل"], "description_fa": "نام خانوادگی شخص."},
    "organization_unit_id": {"display_name_fa": "واحد سازمانی", "aliases_fa": ["واحد سازمانی", "محل خدمت", "منطقه"], "description_fa": "شناسه واحد سازمانی مرتبط."},
    "position": {"display_name_fa": "شغل", "aliases_fa": ["شغل", "سمت", "عنوان شغلی", "پست"], "description_fa": "عنوان شغلی کارمند."},
    "hire_date": {"display_name_fa": "تاریخ استخدام", "aliases_fa": ["تاریخ استخدام", "شروع کار"], "description_fa": "تاریخ استخدام کارمند."},
    "status": {"display_name_fa": "وضعیت", "aliases_fa": ["وضعیت", "فعال", "غیرفعال"], "description_fa": "وضعیت رکورد مانند active یا inactive."},
    "created_at": {"display_name_fa": "زمان ثبت", "aliases_fa": ["تاریخ ایجاد", "زمان ثبت"], "description_fa": "زمان ایجاد رکورد."},
    "school_id": {"display_name_fa": "مدرسه", "aliases_fa": ["مدرسه", "نام مدرسه"], "description_fa": "شناسه مدرسه دانش‌آموز."},
    "grade": {"display_name_fa": "پایه", "aliases_fa": ["پایه", "مقطع", "کلاس"], "description_fa": "پایه یا مقطع تحصیلی دانش‌آموز."},
    "enrollment_year": {"display_name_fa": "سال ثبت‌نام", "aliases_fa": ["سال ثبت‌نام", "سال ثبت نام"], "description_fa": "سال ثبت‌نام دانش‌آموز."},
    "name": {"display_name_fa": "نام", "aliases_fa": ["نام", "اسم"], "description_fa": "نام رکورد یا موجودیت."},
    "school_type": {"display_name_fa": "نوع مدرسه", "aliases_fa": ["نوع مدرسه", "مقطع مدرسه"], "description_fa": "نوع مدرسه مانند دبستان، دبیرستان یا هنرستان."},
    "capacity": {"display_name_fa": "ظرفیت", "aliases_fa": ["ظرفیت", "گنجایش"], "description_fa": "ظرفیت مدرسه."},
    "established_year": {"display_name_fa": "سال تأسیس", "aliases_fa": ["سال تأسیس", "سال تاسیس"], "description_fa": "سال تأسیس مدرسه."},
    "address": {"display_name_fa": "آدرس", "aliases_fa": ["آدرس", "نشانی"], "description_fa": "آدرس یا نشانی مدرسه."},
    "phone": {"display_name_fa": "تلفن", "aliases_fa": ["تلفن", "شماره تلفن", "شماره تماس"], "description_fa": "شماره تلفن یا تماس."},
    "unit_type": {"display_name_fa": "نوع واحد", "aliases_fa": ["نوع واحد", "نوع"], "description_fa": "نوع واحد سازمانی مانند province یا district."},
    "parent_id": {"display_name_fa": "واحد بالادستی", "aliases_fa": ["والد", "واحد بالادستی", "زیرمجموعه"], "description_fa": "شناسه واحد سازمانی بالادستی."},
    "province": {"display_name_fa": "استان", "aliases_fa": ["استان"], "description_fa": "نام استان."},
    "city": {"display_name_fa": "شهر", "aliases_fa": ["شهر", "منطقه"], "description_fa": "نام شهر یا منطقه."},
    "year": {"display_name_fa": "سال", "aliases_fa": ["سال"], "description_fa": "سال مربوط به رکورد."},
    "month": {"display_name_fa": "ماه", "aliases_fa": ["ماه"], "description_fa": "ماه مربوط به رکورد."},
    "base_salary": {"display_name_fa": "حقوق پایه", "aliases_fa": ["حقوق پایه", "پایه حقوق"], "description_fa": "مبلغ حقوق پایه."},
    "allowances": {"display_name_fa": "مزایا", "aliases_fa": ["مزایا", "فوق‌العاده"], "description_fa": "مبلغ مزایا."},
    "deductions": {"display_name_fa": "کسورات", "aliases_fa": ["کسورات", "کسر"], "description_fa": "مبلغ کسورات."},
    "net_salary": {"display_name_fa": "حقوق خالص", "aliases_fa": ["حقوق خالص", "پرداختی خالص"], "description_fa": "حقوق خالص پرداختی."},
    "payment_date": {"display_name_fa": "تاریخ پرداخت", "aliases_fa": ["تاریخ پرداخت"], "description_fa": "تاریخ پرداخت حقوق."},
    "request_date": {"display_name_fa": "تاریخ درخواست", "aliases_fa": ["تاریخ درخواست"], "description_fa": "تاریخ ثبت درخواست."},
    "ranking_type": {"display_name_fa": "نوع رتبه‌بندی", "aliases_fa": ["نوع رتبه", "نوع رتبه‌بندی"], "description_fa": "نوع رتبه‌بندی یا ارتقا."},
    "current_rank": {"display_name_fa": "رتبه فعلی", "aliases_fa": ["رتبه فعلی"], "description_fa": "رتبه فعلی کارمند."},
    "requested_rank": {"display_name_fa": "رتبه درخواستی", "aliases_fa": ["رتبه درخواستی"], "description_fa": "رتبه درخواستی کارمند."},
    "review_date": {"display_name_fa": "تاریخ بررسی", "aliases_fa": ["تاریخ بررسی"], "description_fa": "تاریخ بررسی درخواست."},
    "retirement_date": {"display_name_fa": "تاریخ بازنشستگی", "aliases_fa": ["تاریخ بازنشستگی"], "description_fa": "تاریخ بازنشستگی کارمند."},
    "retirement_type": {"display_name_fa": "نوع بازنشستگی", "aliases_fa": ["نوع بازنشستگی"], "description_fa": "نوع بازنشستگی."},
    "years_of_service": {"display_name_fa": "سابقه خدمت", "aliases_fa": ["سابقه خدمت", "سال خدمت"], "description_fa": "تعداد سال‌های خدمت کارمند."},
    "pension_amount": {
        "display_name_fa": "سنوات پرداخت‌شده",
        "aliases_fa": ["سنوات", "مبلغ سنوات", "سنوات پرداخت شده", "مستمری"],
        "description_fa": "مبلغ سنوات/مستمری پرداخت‌شده به کارمند.",
        "confidence": 0.95,
    },
    "reason": {"display_name_fa": "علت", "aliases_fa": ["علت", "دلیل"], "description_fa": "علت یا توضیح رکورد."},
    "requester_name": {
        "display_name_fa": "نام درخواست‌دهنده",
        "aliases_fa": ["نام درخواست‌دهنده", "درخواست‌دهنده", "ثبت‌کننده درخواست", "نام متقاضی"],
        "description_fa": "نام شخصی که درخواست آموزشی را ثبت کرده است.",
        "confidence": 0.95,
    },
    "requester_role": {
        "display_name_fa": "نقش درخواست‌دهنده",
        "aliases_fa": ["نقش درخواست‌دهنده", "سمت درخواست‌دهنده", "نقش متقاضی", "سمت متقاضی"],
        "description_fa": "نقش یا سمت شخص درخواست‌دهنده مانند مدیر مدرسه، معلم یا کارمند اداری.",
        "confidence": 0.95,
    },
    "request_type": {
        "display_name_fa": "نوع درخواست آموزشی",
        "aliases_fa": ["نوع درخواست", "نوع دوره", "موضوع دوره", "عنوان دوره", "کارگاه", "دوره"],
        "description_fa": "نوع یا موضوع درخواست آموزشی مانند کارگاه هوش مصنوعی یا دوره ضمن خدمت معلمان.",
        "confidence": 0.95,
    },
    "priority": {
        "display_name_fa": "اولویت",
        "aliases_fa": ["اولویت", "فوریت", "میزان اهمیت", "اولویت بالا", "کم‌اولویت"],
        "description_fa": "اولویت رسیدگی به درخواست آموزشی؛ مانند high، normal یا low.",
        "confidence": 0.95,
    },
    "assigned_unit": {
        "display_name_fa": "واحد مسئول",
        "aliases_fa": ["واحد مسئول", "واحد رسیدگی‌کننده", "اداره مسئول", "مرکز مسئول"],
        "description_fa": "واحد سازمانی مسئول رسیدگی به درخواست آموزشی.",
        "confidence": 0.95,
    },
    "estimated_cost": {
        "display_name_fa": "هزینه برآوردی",
        "aliases_fa": ["هزینه", "هزینه برآوردی", "مبلغ", "بودجه", "هزینه تخمینی"],
        "description_fa": "هزینه یا بودجه برآوردشده برای درخواست آموزشی.",
        "confidence": 0.95,
    },
    "requested_at": {
        "display_name_fa": "تاریخ درخواست",
        "aliases_fa": ["تاریخ درخواست", "زمان درخواست", "تاریخ ثبت درخواست"],
        "description_fa": "تاریخ ثبت درخواست آموزشی.",
        "confidence": 0.95,
    },
}


class SemanticSuggestionService:
    def __init__(self):
        self.settings = get_settings()
        self.schema_root = Path(__file__).parent.parent.parent / "schema" / "tenants"

    def _tenant_dir(self, tenant_id: str) -> Path:
        tenant_dir = self.schema_root / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir

    def _load_discovery(self, tenant_id: str) -> SchemaDiscoverySnapshot:
        path = self._tenant_dir(tenant_id) / "discovery.json"
        with path.open("r", encoding="utf-8") as file:
            return SchemaDiscoverySnapshot.model_validate(json.load(file))

    def _load_existing_active_catalog(self, tenant_id: str) -> SemanticCatalog | None:
        path = self._tenant_dir(tenant_id) / "semantic_active.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            return SemanticCatalog.model_validate(json.load(file))

    def _fallback_display_name(self, name: str) -> str:
        return name.replace("_", " ")

    def _existing_columns(self, table: DiscoveredTableInfo, candidates: Iterable[str]) -> list[str]:
        available = {column.name for column in table.columns}
        return [candidate for candidate in candidates if candidate in available]

    def _clamp_confidence(self, value: float) -> float:
        return round(max(0.05, min(0.99, value)), 2)

    def _column_confidence(self, column: DiscoveredColumnInfo, known: dict) -> tuple[float, list[str]]:
        score = 0.35
        reasons = []
        if known:
            score += 0.35
            reasons.append("known_column_mapping")
        else:
            reasons.append("heuristic_column_mapping")
        if column.comment:
            score += 0.08
            reasons.append("database_comment")
        if column.sample_values:
            score += 0.12
            reasons.append("sample_values_available")
        elif column.data_type in {"character varying", "character", "text", "USER-DEFINED"} and not column.name.endswith("_id"):
            score -= 0.12
            reasons.append("missing_text_sample_values")
        if column.is_primary_key or column.is_unique:
            score += 0.06
            reasons.append("key_or_unique_column")
        if column.name.endswith("_id") and not column.is_primary_key:
            score += 0.04
            reasons.append("relationship_like_column")
        if known.get("pii"):
            score -= 0.04
            reasons.append("pii_requires_policy")
        if known.get("confidence") is not None:
            score = max(score, float(known["confidence"]))
        return self._clamp_confidence(score), reasons

    def _table_confidence(
        self,
        table: DiscoveredTableInfo,
        known: dict,
        columns: list[SemanticColumnSuggestion],
    ) -> tuple[float, list[str]]:
        score = 0.3
        reasons = []
        if known:
            score += 0.35
            reasons.append("known_table_mapping")
        else:
            reasons.append("heuristic_table_mapping")
        if table.primary_keys:
            score += 0.12
            reasons.append("primary_key_available")
        else:
            score -= 0.15
            reasons.append("missing_primary_key")
        if table.foreign_keys:
            score += 0.08
            reasons.append("foreign_keys_available")
        elif table.row_count > 0:
            score -= 0.04
            reasons.append("no_foreign_keys")
        if table.comment:
            score += 0.06
            reasons.append("database_comment")
        if any(column.confidence >= 0.8 for column in columns):
            score += 0.08
            reasons.append("high_confidence_columns")
        if any(column.confidence < 0.55 for column in columns):
            score -= 0.08
            reasons.append("low_confidence_columns")
        if known.get("confidence") is not None:
            score = max(score, float(known["confidence"]))
        return self._clamp_confidence(score), reasons

    def _suggest_column(self, column: DiscoveredColumnInfo) -> SemanticColumnSuggestion:
        known = KNOWN_COLUMNS.get(column.name, {})
        confidence, reasons = self._column_confidence(column, known)
        return SemanticColumnSuggestion(
            name=column.name,
            data_type=column.data_type,
            display_name_fa=known.get("display_name_fa", self._fallback_display_name(column.name)),
            description_fa=known.get("description_fa", f"ستون {column.name} از نوع {column.data_type}."),
            aliases_fa=known.get("aliases_fa", [self._fallback_display_name(column.name)]),
            value_type=known.get("value_type"),
            pii=bool(known.get("pii", False)),
            confidence=confidence,
            confidence_reasons=reasons,
            source="known_mapping" if known else "heuristic",
        )

    def _suggest_table(self, table: DiscoveredTableInfo) -> SemanticTableSuggestion:
        known = KNOWN_TABLES.get(table.name, {})
        primary_key = table.primary_keys[0] if table.primary_keys else "id"
        default_display = self._existing_columns(
            table,
            known.get("default_display_columns", ["name", "first_name", "last_name", primary_key]),
        )
        profile_columns = self._existing_columns(
            table,
            known.get("profile_columns", [column.name for column in table.columns]),
        )
        columns = [self._suggest_column(column) for column in table.columns]
        confidence, reasons = self._table_confidence(table, known, columns)
        return SemanticTableSuggestion(
            name=table.name,
            entity=known.get("entity", table.name),
            display_name_fa=known.get("display_name_fa", self._fallback_display_name(table.name)),
            description_fa=known.get("description_fa", f"جدول {table.name} با {table.row_count} ردیف."),
            aliases_fa=known.get("aliases_fa", [self._fallback_display_name(table.name)]),
            primary_key=primary_key,
            default_display_columns=default_display,
            profile_columns=profile_columns,
            row_count=table.row_count,
            confidence=confidence,
            confidence_reasons=reasons,
            review_required=confidence < 0.85,
            columns=columns,
        )

    def _merge_existing_reviews(
        self,
        suggestions: SemanticSuggestionSet,
        existing_catalog: SemanticCatalog | None,
    ) -> SemanticSuggestionSet:
        if existing_catalog is None:
            return suggestions

        existing_tables = {
            normalize_identifier(table.name): table
            for table in existing_catalog.tables
        }
        for suggestion in suggestions.tables:
            existing_table = existing_tables.get(normalize_identifier(suggestion.name))
            if existing_table is None:
                continue

            suggestion.aliases_fa = self._merge_unique(suggestion.aliases_fa, existing_table.aliases)
            if existing_table.description and suggestion.description_fa == self._fallback_display_name(suggestion.name):
                suggestion.description_fa = existing_table.description

            existing_columns = {
                normalize_identifier(column.name): column
                for column in existing_table.columns
            }
            for column_suggestion in suggestion.columns:
                existing_column = existing_columns.get(normalize_identifier(column_suggestion.name))
                if existing_column is None:
                    continue
                column_suggestion.aliases_fa = self._merge_unique(column_suggestion.aliases_fa, existing_column.aliases)
                if existing_column.value_type and not column_suggestion.value_type:
                    column_suggestion.value_type = existing_column.value_type
                if existing_column.pii:
                    column_suggestion.pii = True

        return suggestions

    def _merge_unique(self, current: list[str], previous: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in [*current, *previous]:
            normalized = normalize_identifier(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(value)
        return merged

    def _suggest_joins(self, snapshot: SchemaDiscoverySnapshot) -> list[SemanticJoinSuggestion]:
        descriptions = {
            ("employees", "organization_unit_id", "organization_units", "id"): "هر کارمند به یک واحد سازمانی وصل است.",
            ("schools", "organization_unit_id", "organization_units", "id"): "هر مدرسه به یک واحد یا منطقه سازمانی وصل است.",
            ("students", "school_id", "schools", "id"): "هر دانش‌آموز به یک مدرسه وصل است.",
            ("salary_items", "employee_id", "employees", "id"): "هر آیتم حقوقی مربوط به یک کارمند است.",
            ("ranking_requests", "employee_id", "employees", "id"): "هر درخواست رتبه‌بندی مربوط به یک کارمند است.",
            ("retirement_records", "employee_id", "employees", "id"): "هر سابقه بازنشستگی مربوط به یک کارمند است.",
            ("organization_units", "parent_id", "organization_units", "id"): "هر واحد سازمانی می‌تواند زیرمجموعه یک واحد بالادستی باشد.",
        }
        return [
            SemanticJoinSuggestion(
                from_table=relationship.source_table,
                from_column=relationship.source_column,
                to_table=relationship.target_table,
                to_column=relationship.target_column,
                description_fa=descriptions.get(
                    (
                        relationship.source_table,
                        relationship.source_column,
                        relationship.target_table,
                        relationship.target_column,
                    ),
                    f"{relationship.source_table}.{relationship.source_column} به {relationship.target_table}.{relationship.target_column} وصل است.",
                ),
                cardinality=relationship.relationship_type,
                confidence=0.95 if (
                    relationship.source_table,
                    relationship.source_column,
                    relationship.target_table,
                    relationship.target_column,
                ) in descriptions else 0.8,
            )
            for relationship in snapshot.relationships
        ]

    def _business_terms(self, table_names: set[str]) -> list[SemanticBusinessTermSuggestion]:
        terms = []
        if "retirement_records" in table_names:
            terms.append(
                SemanticBusinessTermSuggestion(
                    term_fa="سنوات",
                    aliases_fa=["سنوات پرداخت‌شده", "مبلغ سنوات", "مستمری"],
                    maps_to="retirement_records.pension_amount",
                    description_fa="در این سیستم منظور کاربر از سنوات، ستون pension_amount در جدول retirement_records است.",
                    confidence=0.95,
                    review_required=False,
                )
            )
            terms.append(
                SemanticBusinessTermSuggestion(
                    term_fa="سابقه خدمت",
                    aliases_fa=["سال خدمت", "تعداد سال خدمت"],
                    maps_to="retirement_records.years_of_service",
                    description_fa="برای تعداد سال‌های خدمت از years_of_service استفاده شود، نه pension_amount.",
                    confidence=0.9,
                    review_required=False,
                )
            )
        return terms

    def _value_mappings(self, table_names: set[str]) -> list[SemanticValueMappingSuggestion]:
        mappings = []
        for table in sorted(table_names & {"employees", "students"}):
            mappings.append(
                SemanticValueMappingSuggestion(
                    term_fa="فعال",
                    aliases_fa=["اکتیو", "active", "در حال فعالیت"],
                    column=f"{table}.status",
                    value="active",
                    description_fa="کلمه فعال در سؤال کاربر به مقدار دیتابیسی active تبدیل شود.",
                    confidence=0.95,
                )
            )
        if "demo_training_requests" in table_names:
            for term_fa, aliases_fa, column, value, description_fa in [
                ("فعال", ["active", "باز", "در حال رسیدگی"], "demo_training_requests.status", "active", "درخواست آموزشی فعال یا باز به مقدار active نگاشت شود."),
                ("تایید شده", ["تأیید شده", "approved", "مصوب", "قبول شده"], "demo_training_requests.status", "approved", "درخواست آموزشی تایید شده به مقدار approved نگاشت شود."),
                ("در انتظار بررسی", ["pending", "منتظر بررسی", "در انتظار", "بررسی نشده"], "demo_training_requests.status", "pending", "درخواست آموزشی در انتظار بررسی به مقدار pending نگاشت شود."),
                ("رد شده", ["rejected", "مردود", "ردشده"], "demo_training_requests.status", "rejected", "درخواست آموزشی رد شده به مقدار rejected نگاشت شود."),
                ("اولویت بالا", ["high", "فوری", "مهم", "با اولویت بالا"], "demo_training_requests.priority", "high", "اولویت بالا یا فوری به مقدار high نگاشت شود."),
                ("اولویت عادی", ["normal", "معمولی", "عادی"], "demo_training_requests.priority", "normal", "اولویت عادی به مقدار normal نگاشت شود."),
                ("کم‌اولویت", ["low", "اولویت پایین", "کم اهمیت"], "demo_training_requests.priority", "low", "کم‌اولویت یا اولویت پایین به مقدار low نگاشت شود."),
            ]:
                mappings.append(
                    SemanticValueMappingSuggestion(
                        term_fa=term_fa,
                        aliases_fa=aliases_fa,
                        column=column,
                        value=value,
                        description_fa=description_fa,
                        confidence=0.95,
                    )
                )
        return mappings

    def _rules(self, table_names: set[str]) -> list[SemanticRuleSuggestion]:
        rules = [
            SemanticRuleSuggestion(
                name="national_id_is_text",
                description_fa="کد ملی در جدول‌های employees و students متنی است و حتی اگر عددی باشد باید در SQL داخل کوتیشن بیاید.",
                applies_to=["employees.national_id", "students.national_id"],
                confidence=0.95,
                review_required=False,
            )
        ]
        if {"students", "schools", "organization_units"}.issubset(table_names):
            rules.append(
                SemanticRuleSuggestion(
                    name="student_province_join_path",
                    description_fa="برای فیلتر استان دانش‌آموز باید مسیر students -> schools -> organization_units استفاده شود.",
                    applies_to=["students", "schools", "organization_units"],
                    confidence=0.95,
                    review_required=False,
                )
            )
        if {"schools", "organization_units"}.issubset(table_names):
            rules.append(
                SemanticRuleSuggestion(
                    name="school_province_join_path",
                    description_fa="برای فیلتر استان مدرسه باید schools به organization_units وصل شود.",
                    applies_to=["schools", "organization_units"],
                    confidence=0.95,
                    review_required=False,
                )
            )
        if {"employees", "organization_units"}.issubset(table_names):
            rules.append(
                SemanticRuleSuggestion(
                    name="employee_province_join_path",
                    description_fa="برای فیلتر استان کارمند باید employees به organization_units وصل شود.",
                    applies_to=["employees", "organization_units"],
                    confidence=0.95,
                    review_required=False,
                )
            )
        return rules

    def generate(self, tenant_id: Optional[str] = None) -> SemanticSuggestionSet:
        tenant = tenant_id or self.settings.tenant_id
        discovery = self._load_discovery(tenant)
        existing_catalog = self._load_existing_active_catalog(tenant)
        table_names = {table.name for table in discovery.tables}
        suggestions = SemanticSuggestionSet(
            tenant_id=tenant,
            source_fingerprint=discovery.fingerprint,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            tables=[self._suggest_table(table) for table in discovery.tables],
            joins=self._suggest_joins(discovery),
            business_terms=self._business_terms(table_names),
            value_mappings=self._value_mappings(table_names),
            rules=self._rules(table_names),
        )
        return self._merge_existing_reviews(suggestions, existing_catalog)

    def save(self, suggestions: SemanticSuggestionSet, output_path: Optional[Path] = None) -> Path:
        path = output_path or self._tenant_dir(suggestions.tenant_id) / "semantic_suggestions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(suggestions.model_dump(), file, ensure_ascii=False, indent=2)
        return path

    def sync(self, tenant_id: Optional[str] = None, output_path: Optional[Path] = None) -> tuple[SemanticSuggestionSet, Path]:
        suggestions = self.generate(tenant_id)
        return suggestions, self.save(suggestions, output_path)


semantic_suggestion_service = SemanticSuggestionService()
