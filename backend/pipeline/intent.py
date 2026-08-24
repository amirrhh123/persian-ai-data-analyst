from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog


class IntentFilter(BaseModel):
    column: str
    operator: str = "="
    value: str
    required: bool = True


class IntentSorting(BaseModel):
    column: str
    direction: str = "DESC"
    required: bool = True


class QueryIntent(BaseModel):
    requested_entity: Optional[str] = None
    aggregation: Optional[str] = None
    filters: list[IntentFilter] = Field(default_factory=list)
    grouping: list[str] = Field(default_factory=list)
    sorting: Optional[IntentSorting] = None
    limit: Optional[int] = None
    date_range: Optional[dict[str, Optional[int]]] = None
    named_school: Optional[str] = None
    named_student: Optional[str] = None
    named_organization_unit: Optional[str] = None
    named_employee: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    national_id: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    province_values: list[str] = Field(default_factory=list)
    city_values: list[str] = Field(default_factory=list)
    status: Optional[str] = None
    position: Optional[str] = None
    hire_year: Optional[int] = None
    school_type: Optional[str] = None
    capacity_min: Optional[int] = None
    established_year: Optional[int] = None
    grade: Optional[str] = None
    enrollment_year: Optional[int] = None
    wants_phone: bool = False
    wants_full_profile: bool = False
    wants_service_years: bool = False
    wants_school_name: bool = False
    wants_list: bool = False
    ranking_metric: Optional[str] = None
    requested_columns: list[str] = Field(default_factory=list)
    semantic_metrics: list[str] = Field(default_factory=list)


class NormalizedIntentFilter(BaseModel):
    field: str
    operator: str = "="
    value: str
    source: str = "intent"


class NormalizedIntent(BaseModel):
    entity: Optional[str] = None
    operation: str = "list"
    filters: list[NormalizedIntentFilter] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    requested_columns: list[str] = Field(default_factory=list)
    sort: Optional[IntentSorting] = None
    limit: Optional[int] = None
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class AmbiguityResult(BaseModel):
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


ENTITY_PRIORITY = {
    "salary": 90,
    "school": 80,
    "student": 70,
    "employee": 60,
    "ranking_request": 50,
    "retirement_record": 40,
    "organization_unit": 30,
}

ENTITY_TO_REQUESTED = {
    "employee": "employee",
    "student": "student",
    "school": "school",
    "organization_unit": "organization",
    "salary": "salary",
    "ranking_request": "ranking",
    "retirement_record": "retirement",
}

STATUS_VALUE_MAP = {
    "غیرفعال": "inactive",
    "تایید نشده": "pending",
    "تأیید نشده": "pending",
    "در انتظار": "pending",
    "تایید شده": "approved",
    "تأیید شده": "approved",
    "رد شده": "rejected",
    "فعال": "active",
}

PERSIAN_MONTHS = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "آذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}

PROVINCES = [
    "آذربایجان شرقی",
    "اصفهان",
    "تهران",
    "خراسان رضوی",
    "خوزستان",
    "سیستان و بلوچستان",
    "فارس",
    "مازندران",
    "کرمان",
    "گیلان",
]

CITIES = [
    "آبادان",
    "آمل",
    "اصفهان",
    "انزلی",
    "اهر",
    "اهواز",
    "بابل",
    "تبریز",
    "تربت حیدریه",
    "تهران",
    "جهرم",
    "جیرفت",
    "خرمشهر",
    "رشت",
    "رفسنجان",
    "ری",
    "زابل",
    "زاهدان",
    "ساری",
    "شهرری",
    "شیراز",
    "لاهیجان",
    "مراغه",
    "مرودشت",
    "مشهد",
    "نائین",
    "نیشابور",
    "چابهار",
    "کاشان",
    "کرمان",
]

REFERENTIAL_PATTERNS = [
    "یک مدرسه خاص",
    "یک منطقه خاص",
    "این منطقه",
    "آن منطقه",
    "همان منطقه",
    "این مدرسه",
    "آن مدرسه",
    "همان مدرسه",
    "این واحد",
    "آن واحد",
    "همان واحد",
    "این کارمند",
    "آن کارمند",
    "این استان",
    "آن استان",
    "مورد مذکور",
    "واحد مذکور",
    "مدرسه مذکور",
    "بازه موردنظر",
]

SERVICE_YEAR_PHRASES = [
    "سنوات خدمت",
    "سابقه خدمت",
    "مدت خدمت",
    "چند سال سابقه",
]


def normalize_persian(text: str) -> str:
    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "\u200f": "",
        "\u200e": "",
    }
    normalized = text
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_alias(question: str, alias: str) -> bool:
    alias = normalize_persian(alias).lower()
    question = question.lower()
    if " " in alias or "\u200c" in alias:
        return alias in question
    return re.search(rf"(?<![\wآ-ی]){re.escape(alias)}(?![\wآ-ی])", question) is not None


def _detect_entity(q: str, semantic_catalog: SemanticCatalog) -> Optional[str]:
    matches: list[tuple[int, str]] = []
    for table in semantic_catalog.tables:
        if any(_contains_alias(q, alias) for alias in table.aliases):
            requested = ENTITY_TO_REQUESTED.get(table.entity)
            if requested:
                matches.append((ENTITY_PRIORITY.get(table.entity, 0), requested))

    if not matches:
        return None
    return sorted(matches, reverse=True)[0][1]


def _detect_requested_columns(
    q: str,
    requested_entity: Optional[str],
    semantic_catalog: SemanticCatalog,
) -> list[str]:
    if not requested_entity:
        return []

    table = next(
        (
            item
            for item in semantic_catalog.tables
            if ENTITY_TO_REQUESTED.get(item.entity) == requested_entity
        ),
        None,
    )
    if not table:
        return []

    requested_columns: list[str] = []
    for column in table.columns:
        if any(_contains_alias(q, alias) for alias in column.aliases):
            requested_columns.append(column.name)

    return list(dict.fromkeys(requested_columns))


def _extract_national_id(q: str) -> Optional[str]:
    match = re.search(r"(?:کد\s*ملی|شناسه\s*ملی|شماره\s*ملی|ملی)\s*[\"'«»]?\s*([0-9۰-۹]{10})\s*[\"'«»]?", q)
    if not match:
        return None
    return match.group(1).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def _to_ascii_digits(value: str) -> str:
    return value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def _extract_temporal_filters(q: str) -> dict[str, Optional[int]]:
    filters: dict[str, Optional[int]] = {"year": None, "month": None}

    year_match = re.search(r"سال\s+([0-9۰-۹]{4})", q)
    if year_match:
        filters["year"] = int(_to_ascii_digits(year_match.group(1)))

    month_number_match = re.search(r"ماه\s+([0-9۰-۹]{1,2})", q)
    if month_number_match:
        month = int(_to_ascii_digits(month_number_match.group(1)))
        if 1 <= month <= 12:
            filters["month"] = month

    for month_name, month_number in PERSIAN_MONTHS.items():
        if re.search(rf"(?<![آ-ی]){re.escape(month_name)}(?![آ-ی])", q):
            filters["month"] = month_number
            break

    return filters


def _extract_limit(q: str) -> Optional[int]:
    match = re.search(r"(?<![0-9۰-۹])([0-9۰-۹]{1,2})\s*(?:تا|مورد|استان|شهر|مدرسه|کارمند|دانش\s*آموز|دانش‌آموز)", q)
    if not match:
        return None
    value = int(_to_ascii_digits(match.group(1)))
    return value if 1 <= value <= 50 else None


_PERSON_NAME_STOPWORDS = {
    "استان", "شهر", "مدرسه", "منطقه", "دانش", "دانش‌آموز", "دانش آموز",
    "کارمند", "کارکنان", "پرسنل", "معلم", "دبیر", "مدیر", "هنرستان",
}

# Particles/prepositions that regex capture groups can swallow before a real
# name appears; two-letter Persian tokens are effectively never given names.
_PERSON_NAME_PARTICLES = {
    "با", "از", "در", "به", "را", "و", "که", "برای", "تا", "هم", "یا",
    "این", "آن", "های", "ها", "است", "بود", "شود",
}


def _valid_person_name_token(token: Optional[str]) -> bool:
    if not token:
        return False
    cleaned = token.strip()
    return len(cleaned) >= 3 and cleaned not in _PERSON_NAME_STOPWORDS and cleaned not in _PERSON_NAME_PARTICLES


def _extract_person_name_filters(q: str, entity: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if entity not in {"student", "employee", "salary", "retirement", "ranking"}:
        return None, None

    first_name = None
    last_name = None

    first_match = re.search(r"(?:اسم|نام)(?!\s+خانوادگی)\s*(?:او|آن\s*ها|آن‌ها|شان|ش|دانش\s*آموز|دانش‌آموز|کارمند)?\s+([آ-ی]{2,})", q)
    if first_match:
        candidate = first_match.group(1)
        if _valid_person_name_token(candidate):
            first_name = candidate

    last_match = re.search(r"(?:فامیل|نام\s+خانوادگی)\s*(?:او|آن\s*ها|آن‌ها|شان|ش)?\s+([آ-ی]{2,})", q)
    if last_match:
        candidate = last_match.group(1)
        # Role nouns like «کارمند» describe the entity, not a family name;
        # without this guard the word leaks into required-filter contracts.
        if _valid_person_name_token(candidate):
            last_name = candidate

    entity_word = r"دانش\s*آموز|دانش‌آموز" if entity == "student" else r"کارمند|کارکن|پرسنل|معلم|دبیر"
    full_name_match = re.search(rf"(?:{entity_word})\s+([آ-ی]{{2,}})\s+([آ-ی]{{2,}})(?:\s+را|\s+رو|\s+با|\s+که|\s+در|\s+از|\s+پایه|\s+وضعیت|\s+شغل|\s+فعال|\s+غیرفعال|\s+شهر|\s+استان|\s+چیست|\s+چیه|$)", q)
    if (
        full_name_match
        and _valid_person_name_token(full_name_match.group(1))
        and _valid_person_name_token(full_name_match.group(2))
        and not any(term in full_name_match.group(1) for term in {"استان", "شهر", "مدرسه"})
    ):
        first_name = first_name or full_name_match.group(1)
        last_name = last_name or full_name_match.group(2)

    by_name_match = re.search(
        r"(?:با|برای)\s+(?:نام|اسم)\s+([\u0600-\u06FF]{2,})\s+([\u0600-\u06FF]{2,})(?:\s+را|\s+رو|\s+بده|\s+نشان|\s+نمایش|$)",
        q,
    )
    if (
        by_name_match
        and _valid_person_name_token(by_name_match.group(1))
        and _valid_person_name_token(by_name_match.group(2))
    ):
        first_name = first_name or by_name_match.group(1)
        last_name = last_name or by_name_match.group(2)

    if entity == "ranking":
        ranking_name_match = re.search(
            r"(?:رتبه\s*بندی|رتبه‌بندی)\s+([\u0600-\u06FF]{2,})\s+([\u0600-\u06FF]{2,})",
            q,
        )
        if (
            ranking_name_match
            and _valid_person_name_token(ranking_name_match.group(1))
            and _valid_person_name_token(ranking_name_match.group(2))
        ):
            first_name = first_name or ranking_name_match.group(1)
            last_name = last_name or ranking_name_match.group(2)

    return first_name, last_name


def extract_intent(
    question: str,
    semantic_catalog: SemanticCatalog | None = None,
) -> QueryIntent:
    q = normalize_persian(question)
    catalog = semantic_catalog or load_tenant_semantic_catalog()
    intent = QueryIntent()

    intent.requested_entity = _detect_entity(q, catalog)

    if ("دانش آموز" in q or "دانش‌آموز" in q) and any(
        school_word in q for school_word in ["مدرسه", "دبیرستان", "دبستان", "هنرستان"]
    ):
        intent.requested_entity = "student"
    if "دانش آموز" in q or "دانش‌آموز" in q:
        intent.requested_entity = "student"
    if "کارمند" in q or "کارمندان" in q or "کارکنان" in q:
        intent.requested_entity = "employee"
    if "مدرسه" in q or "مدارس" in q or "دبیرستان" in q or "دبستان" in q or "هنرستان" in q:
        if intent.requested_entity != "student":
            intent.requested_entity = "school"
    if "سنوات" in q and "پرداخت" in q:
        intent.requested_entity = "retirement"
        intent.wants_service_years = True
        intent.ranking_metric = "pension_amount"
    elif any(phrase in q for phrase in ["حقوق", "پرداختی", "فیش حقوقی"]):
        intent.requested_entity = "salary"
    if any(phrase in q for phrase in SERVICE_YEAR_PHRASES) and intent.requested_entity != "salary":
        intent.requested_entity = "employee"
        intent.wants_service_years = True
    if "رتبه بندی" in q or "رتبه‌بندی" in q or "ارتقا" in q:
        intent.requested_entity = "ranking"

    if "سنوات" in q and "پرداخت" not in q and intent.requested_entity != "salary":
        intent.requested_entity = "employee"
        intent.wants_service_years = True

    if "تعداد" in q or "چندتا" in q or "چند تا" in q or "چند نفر" in q or q.startswith("چند "):
        intent.aggregation = "COUNT"
    if "میانگین" in q:
        intent.aggregation = "AVG"
    if "مجموع" in q:
        intent.aggregation = "SUM"
    if "بیشترین" in q or "بالاترین" in q:
        ranking_column = {
            "salary": "net_salary",
            "student": "student_count",
            "school": "student_count" if any(term in q for term in ["دانش آموز", "دانش‌آموز"]) else "school_count",
            "employee": "employee_count",
            "retirement": "pension_amount",
        }.get(intent.requested_entity or "", "row_count")
        if intent.requested_entity == "salary" and intent.aggregation is None:
            intent.aggregation = "SUM"
        elif intent.requested_entity in {"student", "school", "employee"}:
            intent.aggregation = "COUNT"
        intent.sorting = IntentSorting(column=ranking_column, direction="DESC")
        intent.limit = None if "در هر" in q else (_extract_limit(q) or 1)
    if "کمترین" in q or "پایین‌ترین" in q or "پایین ترین" in q:
        ranking_column = {
            "salary": "net_salary",
            "student": "student_count",
            "school": "school_count",
            "employee": "employee_count",
            "retirement": "pension_amount",
        }.get(intent.requested_entity or "", "row_count")
        if intent.requested_entity == "salary" and intent.aggregation is None:
            intent.aggregation = "SUM"
        elif intent.requested_entity in {"student", "school", "employee"}:
            intent.aggregation = "COUNT"
        intent.sorting = IntentSorting(column=ranking_column, direction="ASC")
        intent.limit = _extract_limit(q) or 1
    if intent.requested_entity == "retirement" and intent.ranking_metric == "pension_amount" and intent.sorting:
        intent.aggregation = None
        intent.sorting.column = "retirement_records.pension_amount"

    if "هر استان" in q or "به تفکیک استان" in q:
        intent.grouping.append("province")
    if "هر شهر" in q or "به تفکیک شهر" in q or "هر منطقه" in q or "به تفکیک منطقه" in q:
        intent.grouping.append("city")
    if intent.sorting and not intent.grouping:
        if "استان" in q:
            intent.grouping.append("province")
        elif "شهر" in q or "منطقه" in q:
            intent.grouping.append("city")
    if intent.sorting and intent.grouping and intent.aggregation == "SUM" and intent.requested_entity != "salary":
        intent.aggregation = "COUNT"

    if any(phrase in q for phrase in ["شماره تلفن", "تلفن", "شماره تماس"]):
        intent.wants_phone = True
        if intent.requested_entity is None:
            intent.requested_entity = "school"
    if intent.requested_entity == "student" and re.search(r"(?:نام|اسم)\s+مدرسه\s+دانش", q):
        intent.wants_school_name = True
    if any(phrase in q for phrase in ["تمام ستون", "همه ستون", "کل ستون", "پروفایل کامل", "اطلاعات کامل"]):
        intent.wants_full_profile = True
    if "اطلاعات" in q and intent.requested_entity and intent.aggregation is None:
        intent.wants_full_profile = True

    if intent.aggregation is None and any(
        phrase in q for phrase in ["لیست", "فهرست", "نشان بده", "نمایش بده", "اطلاعات", "اسم", "نام"]
    ):
        intent.wants_list = True

    intent.national_id = _extract_national_id(q)
    if intent.national_id and intent.requested_entity is None:
        intent.requested_entity = "employee"

    temporal_filters = _extract_temporal_filters(q)
    if temporal_filters["year"] or temporal_filters["month"]:
        intent.date_range = temporal_filters
        if intent.requested_entity is None and any(term in q for term in ["حقوق", "پرداختی", "فیش حقوقی"]):
            intent.requested_entity = "salary"

    if any(term in q for term in ["جدیدترین", "آخرین", "تازه‌ترین", "تازه ترین"]):
        date_column = {
            "salary": "salary_items.payment_date",
            "employee": "employees.created_at",
            "student": "students.created_at",
            "school": "schools.created_at",
            "retirement": "retirement_records.retirement_date",
            "ranking": "ranking_requests.created_at",
            "organization": "organization_units.created_at",
        }.get(intent.requested_entity or "", "created_at")
        intent.sorting = IntentSorting(column=date_column, direction="DESC")
        intent.limit = intent.limit or 10
    if any(term in q for term in ["قدیمی‌ترین", "قدیمی ترین", "اولین"]):
        date_column = {
            "salary": "salary_items.payment_date",
            "employee": "employees.created_at",
            "student": "students.created_at",
            "school": "schools.created_at",
            "retirement": "retirement_records.retirement_date",
            "ranking": "ranking_requests.created_at",
            "organization": "organization_units.created_at",
        }.get(intent.requested_entity or "", "created_at")
        intent.sorting = IntentSorting(column=date_column, direction="ASC")
        intent.limit = intent.limit or 10

    city_match = re.search(r"(?:شهر|منطقه)\s+([آ-ی]+(?:\s+[آ-ی]+)?)(?:\s+را|\s+را\s|\s+که|\s+با|\s+دارند|\s+دارد|\s+هستند|\s+است|\s+پرداخت|$)", q)
    if city_match:
        candidate_city = city_match.group(1).strip()
        if candidate_city not in {"نشان بده", "نمایش بده", "مقایسه کن", "لیست کن"}:
            intent.city = candidate_city

    province_match = re.search(r"استان\s+([آ-ی]+(?:\s+[آ-ی]+)?)(?:\s+را|\s+را\s|$)", q)
    if province_match:
        explicit_province = province_match.group(1).strip()
        for province in PROVINCES:
            if province == explicit_province or province.startswith(explicit_province):
                intent.province = province
                break
    elif not intent.city:
        for province in PROVINCES:
            if province in q:
                intent.province = province
                break

    matched_provinces = [province for province in PROVINCES if province in q]
    if len(matched_provinces) >= 2:
        intent.province_values = matched_provinces
        intent.province = None
        if "province" not in intent.grouping:
            intent.grouping.append("province")
        if intent.aggregation is None:
            intent.aggregation = "COUNT"

    explicit_city_values = re.findall(r"شهر\s+([آ-ی]+(?:\s+[آ-ی]+)?)(?=\s+و|\s+را|\s+مقایسه|$)", q)
    command_values = {"نشان بده", "نمایش بده", "مقایسه کن", "لیست کن", "را نشان"}
    explicit_city_values = [value for value in explicit_city_values if value not in command_values]
    matched_cities = list(dict.fromkeys([city for city in CITIES if city in q]))
    if not explicit_city_values and "مقایسه" not in q:
        matched_cities = []
    city_values = list(dict.fromkeys([*explicit_city_values, *matched_cities]))
    if len(city_values) >= 2 and not intent.province_values:
        intent.city_values = city_values
        intent.city = None
        intent.province = None
        if "city" not in intent.grouping:
            intent.grouping.append("city")
        if intent.aggregation is None:
            intent.aggregation = "COUNT"
    elif intent.city:
        intent.province = None

    intent.requested_columns = _detect_requested_columns(q, intent.requested_entity, catalog)
    if intent.aggregation == "COUNT":
        intent.requested_columns = []

    grade_match = re.search(r"پایه\s+([آ-ی0-9۰-۹]+)", q)
    if grade_match and intent.requested_entity == "student":
        intent.grade = grade_match.group(1).strip()
    enrollment_year_match = re.search(r"سال\s+ثبت\s*نام\s+([0-9۰-۹]{4})", q)
    if enrollment_year_match and intent.requested_entity == "student":
        intent.enrollment_year = int(_to_ascii_digits(enrollment_year_match.group(1)))

    position_match = re.search(
        r"(?:با\s+)?(?:شغل|سمت|عنوان\s+شغلی|پست)\s+([آ-ی]+(?:\s+[آ-ی]+)?)(?:\s+را|\s+رو|\s+که|\s+در|\s+استان|\s+شهر|\s+دارند|\s+دارد|\s+هستند|\s+است|\s+فعال|\s+غیرفعال|$)",
        q,
    )
    if position_match and intent.requested_entity in {"employee", "salary"}:
        candidate_position = position_match.group(1).strip()
        if candidate_position not in {"مقایسه کن", "نشان بده", "نمایش بده", "لیست کن"}:
            intent.position = candidate_position
        if "national_id" in intent.requested_columns and "position" in intent.requested_columns:
            intent.requested_columns = [column for column in intent.requested_columns if column != "position"]

    if intent.requested_entity in {"employee", "salary"} and any(
        phrase in q for phrase in ["بر اساس شغل", "براساس شغل", "به تفکیک شغل", "بر اساس سمت", "به تفکیک سمت"]
    ):
        if "position" not in intent.grouping:
            intent.grouping.append("position")

    hire_year_match = re.search(r"سال\s+استخدام\s+([0-9۰-۹]{4})", q)
    if hire_year_match and intent.requested_entity in {"employee", "salary"}:
        intent.hire_year = int(_to_ascii_digits(hire_year_match.group(1)))

    school_type_match = re.search(
        r"(?:نوع\s+مدرسه|مقطع\s+مدرسه)\s+([آ-ی]+(?:\s+[آ-ی]+)?)(?:\s+را|\s+رو|\s+که|\s+در|\s+استان|\s+شهر|\s+با|\s+دارند|\s+دارد|\s+هستند|\s+است|$)",
        q,
    )
    if school_type_match and intent.requested_entity == "school":
        intent.school_type = school_type_match.group(1).strip()
    elif intent.requested_entity == "school":
        for type_value in ["نمونه دولتی", "غیرانتفاعی", "دولتی", "هنرستان", "دبیرستان", "دبستان"]:
            if type_value in q:
                intent.school_type = type_value
                break

    capacity_match = re.search(r"ظرفیت\s+(?:بالای|بیشتر\s+از|حداقل)\s+([0-9۰-۹]+)", q)
    if capacity_match and intent.requested_entity == "school":
        intent.capacity_min = int(_to_ascii_digits(capacity_match.group(1)))

    established_year_match = re.search(r"سال\s+(?:تاسیس|تأسیس)\s+([0-9۰-۹]{4})", q)
    if established_year_match and intent.requested_entity == "school":
        intent.established_year = int(_to_ascii_digits(established_year_match.group(1)))

    first_name, last_name = _extract_person_name_filters(q, intent.requested_entity)
    intent.first_name = first_name
    intent.last_name = last_name
    if intent.requested_entity == "student" and first_name and not intent.national_id:
        intent.named_student = first_name
    if intent.requested_entity == "employee" and (first_name or last_name) and not intent.national_id:
        intent.named_employee = " ".join(part for part in [first_name, last_name] if part)

    school_name_match = re.search(
        r"(?:در\s+)?(?:مدرسه\s+)?((?:دبیرستان|دبستان|هنرستان|مدرسه)\s+.+?)(?:\s+هستند|\s+است|\s+را|\s+در|\s+استان|$)",
        q,
    )
    if school_name_match and intent.requested_entity in {"school", "student"}:
        intent.named_school = school_name_match.group(1).strip()
        if re.search(r"\s+و\s+چند\s+دانش", intent.named_school):
            intent.named_school = None
        if intent.wants_school_name:
            intent.named_school = None
        if intent.named_school and re.search(r"\s+(?:های|ها|های\s+شهر|های\s+استان)\s+", intent.named_school):
            intent.named_school = None
        if intent.named_school and (intent.city or intent.province) and any(term in intent.named_school for term in {"شهر", "استان"}):
            intent.named_school = None
        if intent.named_school and intent.province and intent.province in intent.named_school:
            intent.province = None
    elif intent.requested_entity == "school" and (intent.wants_phone or intent.wants_full_profile):
        school_fragment_match = re.search(
            r"(?:شماره\s+تلفن|تلفن|اطلاعات|مشخصات)\s+(.+?)(?:\s+را|\s+رو|\s+چیست|\s+چیه|$)",
            q,
        )
        if school_fragment_match:
            fragment = school_fragment_match.group(1).strip()
            fragment = re.sub(r"^(?:مدرسه)\s+", "", fragment)
            if fragment and fragment not in {"مدرسه", "مدارس"}:
                intent.named_school = fragment
    elif (
        intent.requested_entity == "student"
        and not intent.province
        and not intent.city
        and not intent.province_values
        and not intent.city_values
        and not intent.grouping
        and not intent.first_name
        and not intent.last_name
    ):
        student_school_fragment_match = re.search(
            r"(?:تعداد\s+)?دانش\s*آموزان\s+(.+?)(?:\s+را|\s+رو|\s+که|\s+هستند|$)",
            q,
        )
        if student_school_fragment_match:
            fragment = student_school_fragment_match.group(1).strip()
            fragment = re.sub(r"^(?:مدرسه)\s+", "", fragment)
            if fragment and not any(term in fragment for term in {"استان", "شهر", "فعال", "غیرفعال", "پایه", "سال ثبت نام", "سال ثبت‌نام"}):
                intent.named_school = fragment

    org_name_match = re.search(
        r"((?:منطقه\s+آموزشی|اداره\s+کل\s+آموزش\s+و\s+پرورش|واحد\s+سازمانی)\s+.+?)(?:\s+را|\s+است|$)",
        q,
    )
    if org_name_match and (intent.requested_entity == "organization" or "منطقه آموزشی" in q):
        intent.named_organization_unit = re.sub(r"^واحد\s+سازمانی\s+", "", org_name_match.group(1).strip())
        if intent.province and intent.province in intent.named_organization_unit:
            intent.province = None

    for persian_term, db_value in STATUS_VALUE_MAP.items():
        if persian_term in q:
            intent.status = db_value
            intent.filters.append(IntentFilter(column="status", value=db_value))
            break

    for filter_column, filter_value in (
        ("province", intent.province),
        ("city", intent.city),
        ("status", intent.status),
        ("position", intent.position),
        ("grade", intent.grade),
        ("school_type", intent.school_type),
    ):
        if filter_value not in (None, "") and filter_column not in intent.grouping:
            intent.requested_columns = [
                column for column in intent.requested_columns if column != filter_column
            ]

    return intent


def suppress_name_substring_columns(
    intent: QueryIntent,
    semantic_catalog: SemanticCatalog,
) -> None:
    """Drop requested columns / type filters whose trigger text sits inside an extracted name.

    General rule (no entity-specific cases): when a semantic alias such as
    «دبیرستان» matched only because it is part of a longer extracted name like
    «دبیرستان فرزانگان مرودشت», it describes the name - not an independent
    requested column or categorical filter. Runs AFTER LLM enrichment so
    late-added columns are covered too.
    """
    name_values = [
        intent.named_school,
        intent.named_organization_unit,
        intent.named_student,
        intent.named_employee,
        intent.first_name,
        intent.last_name,
    ]
    name_texts = [normalize_persian(str(value)).lower() for value in name_values if value]
    if not name_texts:
        return

    column_aliases: dict[str, list[str]] = {}
    for table in semantic_catalog.tables:
        for column in table.columns:
            column_aliases.setdefault(column.name, []).extend(column.aliases or [])

    kept_columns: list[str] = []
    for column in intent.requested_columns:
        aliases = column_aliases.get(column, [])
        substring_of_name = any(
            alias
            and normalize_persian(alias).lower() in text
            for alias in aliases
            for text in name_texts
        )
        if not substring_of_name:
            kept_columns.append(column)
    intent.requested_columns = kept_columns

    if intent.school_type:
        school_type_text = normalize_persian(intent.school_type).lower()
        if any(school_type_text in text for text in name_texts):
            intent.school_type = None

    # Purge structured filter entries whose value merely describes an
    # extracted name (e.g. enrichment adding school_type=دبیرستان when the
    # word دبیرستان is part of the requested school's NAME).
    if intent.filters:
        kept_filters = []
        for item in intent.filters:
            value_text = normalize_persian(str(getattr(item, "value", ""))).lower()
            subsumed = bool(value_text) and any(
                value_text in text and value_text != text for text in name_texts
            )
            if not subsumed:
                kept_filters.append(item)
        intent.filters = kept_filters


def normalize_intent(intent: QueryIntent) -> NormalizedIntent:
    filters: list[NormalizedIntentFilter] = []
    reasons: list[str] = []

    def add_filter(field: str, value: object, operator: str = "=", source: str = "intent") -> None:
        if value is None or value == "":
            return
        filters.append(NormalizedIntentFilter(field=field, operator=operator, value=str(value), source=source))

    add_filter("national_id", intent.national_id, source="national_id")
    add_filter("province", intent.province, source="location")
    add_filter("city", intent.city, source="location")
    for value in intent.province_values:
        add_filter("province", value, source="location_set")
    for value in intent.city_values:
        add_filter("city", value, source="location_set")
    add_filter("status", intent.status, source="status")
    add_filter("position", intent.position, source="position")
    add_filter("first_name", intent.first_name, source="person_name")
    add_filter("last_name", intent.last_name, source="person_name")
    add_filter("grade", intent.grade, source="student")
    add_filter("enrollment_year", intent.enrollment_year, source="student")
    add_filter("school_name", intent.named_school, source="school")
    add_filter("school_type", intent.school_type, source="school")
    add_filter("capacity", intent.capacity_min, operator=">=", source="school")
    add_filter("established_year", intent.established_year, source="school")
    add_filter("organization_unit_name", intent.named_organization_unit, source="organization")
    add_filter("hire_year", intent.hire_year, source="employee")
    if intent.date_range:
        add_filter("year", intent.date_range.get("year"), source="date")
        add_filter("month", intent.date_range.get("month"), source="date")

    has_unique_lookup_filter = bool(intent.national_id) or bool(
        intent.requested_entity in {"school", "organization"} and (intent.named_school or intent.named_organization_unit)
    )
    has_broad_list_filter = bool(
        intent.province
        or intent.city
        or intent.province_values
        or intent.city_values
        or intent.status
        or intent.grade
        or intent.enrollment_year
        or intent.position
        or intent.hire_year
        or intent.school_type
        or intent.capacity_min
        or intent.established_year
        or intent.grouping
    )
    has_partial_person_filter = bool(intent.first_name) != bool(intent.last_name)

    operation = "list"
    if intent.aggregation:
        operation = intent.aggregation.lower()
    elif intent.sorting and intent.limit == 1:
        operation = "rank_one"
    elif intent.wants_full_profile and has_unique_lookup_filter:
        operation = "profile"
    elif intent.wants_phone:
        operation = "lookup"
    elif intent.wants_school_name:
        operation = "lookup"
    elif intent.wants_full_profile and (has_broad_list_filter or has_partial_person_filter):
        operation = "list"
    elif intent.wants_full_profile:
        operation = "profile"
    elif intent.wants_list:
        operation = "list"

    metrics: list[str] = []
    metrics.extend(intent.semantic_metrics)
    if intent.ranking_metric:
        metrics.append(intent.ranking_metric)
    if intent.sorting and intent.sorting.column not in metrics:
        metrics.append(intent.sorting.column)
    if intent.aggregation and not metrics:
        metrics.append("*" if intent.aggregation == "COUNT" else intent.aggregation.lower())

    confidence = 0.35
    if intent.requested_entity:
        confidence += 0.25
        reasons.append("entity_detected")
    if operation != "list" or intent.wants_list or intent.wants_full_profile:
        confidence += 0.15
        reasons.append("operation_detected")
    if filters:
        confidence += 0.15
        reasons.append("filters_detected")
    if intent.requested_columns:
        confidence += 0.05
        reasons.append("requested_columns_detected")
    if intent.grouping:
        confidence += 0.05
        reasons.append("dimensions_detected")

    return NormalizedIntent(
        entity=intent.requested_entity,
        operation=operation,
        filters=filters,
        dimensions=list(dict.fromkeys(intent.grouping)),
        metrics=list(dict.fromkeys(metrics)),
        requested_columns=list(dict.fromkeys(intent.requested_columns)),
        sort=intent.sorting,
        limit=intent.limit,
        confidence=round(min(confidence, 0.99), 2),
        reasons=reasons,
    )


def detect_ambiguity(question: str) -> AmbiguityResult:
    q = normalize_persian(question)
    if any(pattern in q for pattern in REFERENTIAL_PATTERNS):
        if any(term in q for term in ["منطقه", "استان"]):
            clarification = "نام یا کد منطقه/استان موردنظر را مشخص کنید."
        elif "مدرسه" in q:
            clarification = "نام یا کد مدرسه موردنظر را مشخص کنید."
        elif "کارمند" in q:
            clarification = "نام یا کد کارمند موردنظر را مشخص کنید."
        else:
            clarification = "نام یا کد موردنظر را مشخص کنید."
        return AmbiguityResult(
            needs_clarification=True,
            clarification_question=clarification,
        )
    return AmbiguityResult()
