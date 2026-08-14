from __future__ import annotations

import re
from typing import Optional

from backend.database.models import DatabaseSchema
from backend.knowledge.models import Report
from backend.pipeline.intent import QueryIntent
from backend.semantic.models import normalize_identifier
from backend.sql.models import ValidationResult
from backend.sql.structured import ensure_single_select


class SQLValidator:
    FORBIDDEN_KEYWORDS = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
    ]
    IDENTIFIER = r"[a-z_][a-z0-9_۰-۹٠-٩]*"

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_select_only(self, sql: str) -> bool:
        sql_upper = sql.upper()
        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", sql_upper):
                self.errors.append(f"کلمه ممنوعه '{keyword}' در کوئری یافت شد")
                return False

        try:
            ensure_single_select(sql)
        except ValueError as exc:
            self.errors.append(str(exc))
            return False
        return True

    def validate_table_whitelist(
        self,
        sql: str,
        schema: DatabaseSchema,
        report: Optional[Report] = None,
    ) -> bool:
        schema_tables = {normalize_identifier(table.name) for table in schema.tables}
        allowed_tables = set(schema_tables)
        if report:
            allowed_tables = {normalize_identifier(report.linked_table)}
            if report.sql_hints:
                for join in report.sql_hints.preferred_joins:
                    allowed_tables.update(normalize_identifier(table) for table, _ in self._qualified_columns(join))

        for table in self._tables(sql):
            normalized_table = normalize_identifier(table)
            if normalized_table not in schema_tables:
                self.errors.append(f"جدول '{table}' در دیتابیس یافت نشد")
                return False
            if normalized_table not in allowed_tables:
                self.errors.append(f"جدول '{table}' برای این گزارش مجاز نیست")
                return False
        return True

    def validate_columns(self, sql: str, schema: DatabaseSchema) -> bool:
        table_columns = {
            normalize_identifier(table.name): {normalize_identifier(column.name) for column in table.columns}
            for table in schema.tables
        }
        aliases = {
            normalize_identifier(alias): normalize_identifier(table)
            for alias, table in self._aliases(sql).items()
        }

        for qualifier, column in self._qualified_columns(sql):
            normalized_qualifier = normalize_identifier(qualifier)
            normalized_column = normalize_identifier(column)
            table = aliases.get(normalized_qualifier, normalized_qualifier)
            if table not in table_columns:
                self.errors.append(f"جدول یا alias ناشناخته است: {qualifier}")
                return False
            if normalized_column not in table_columns[table]:
                self.errors.append(f"ستون ناشناخته است: {table}.{column}")
                return False

        return True

    def validate_syntax(self, sql: str) -> bool:
        if sql.count("(") != sql.count(")"):
            self.errors.append("پرانتزها نامتقارن هستند")
            return False
        return True

    def validate_complexity(self, sql: str) -> bool:
        normalized = re.sub(r"\s+", " ", sql).strip()
        normalized_lower = normalized.lower()
        ok = True

        if re.search(r"^\s*select\s+\*", normalized_lower):
            self.errors.append("SELECT * مجاز نیست؛ ستون‌های مورد نیاز باید مشخص شوند")
            ok = False

        join_count = len(re.findall(r"\bjoin\b", normalized_lower))
        if join_count > 4:
            self.errors.append("کوئری بیش از حد پیچیده است: تعداد JOINها بیشتر از حد مجاز است")
            ok = False

        limit_match = re.search(r"\blimit\s+(\d+)\b", normalized_lower)
        if limit_match and int(limit_match.group(1)) > 1000:
            self.errors.append("LIMIT بیشتر از ۱۰۰۰ مجاز نیست")
            ok = False

        has_where = bool(re.search(r"\bwhere\b", normalized_lower))
        has_limit = bool(limit_match)
        is_aggregate_or_grouped = bool(
            re.search(r"\b(count|sum|avg|min|max)\s*\(", normalized_lower)
            or re.search(r"\bgroup\s+by\b", normalized_lower)
        )
        if join_count >= 2 and not has_where and not has_limit and not is_aggregate_or_grouped:
            self.errors.append("کوئری لیستی چندجدولی بدون فیلتر یا LIMIT ایمن نیست")
            ok = False

        return ok

    def validate_constraints(self, sql: str, intent: Optional[QueryIntent] = None) -> bool:
        if not intent:
            return True

        normalized = sql.lower()
        for filter_item in intent.filters:
            if not filter_item.required:
                continue
            if filter_item.column.lower() not in normalized or str(filter_item.value).lower() not in normalized:
                self.errors.append(f"فیلتر ضروری در SQL وجود ندارد: {filter_item.column}={filter_item.value}")
                return False

        if intent.national_id and intent.national_id not in normalized:
            self.errors.append(f"فیلتر کد ملی در SQL وجود ندارد: {intent.national_id}")
            return False

        if intent.province and intent.province.lower() not in normalized:
            self.errors.append(f"فیلتر استان در SQL وجود ندارد: {intent.province}")
            return False

        if intent.sorting and "order by" not in normalized:
            self.errors.append("مرتب‌سازی ضروری در SQL وجود ندارد")
            return False

        if intent.limit and not re.search(rf"\blimit\s+{intent.limit}\b", normalized):
            self.errors.append(f"LIMIT ضروری در SQL وجود ندارد: {intent.limit}")
            return False

        for grouping in intent.grouping:
            if "group by" not in normalized or grouping.lower() not in normalized:
                self.errors.append(f"گروه‌بندی ضروری در SQL وجود ندارد: {grouping}")
                return False

        return True

    def validate_semantic_rules(self, sql: str, intent: Optional[QueryIntent] = None) -> bool:
        if not intent:
            return True

        ok = True
        normalized = re.sub(r"\s+", " ", sql.lower()).strip()
        tables = set(self._tables(sql))

        if re.search(r"\b(?:[a-z_][a-z0-9_]*\.)?national_id\s*=\s*[0-9۰-۹]{10}\b", normalized, re.I):
            self.errors.append("کد ملی یک شناسه متنی است و باید در SQL داخل کوتیشن باشد")
            ok = False

        if intent.aggregation == "COUNT" and not re.search(r"\bcount\s*\(", normalized):
            self.errors.append("سؤال تعداد/شمارش است اما SQL از COUNT استفاده نکرده است")
            ok = False
        if intent.wants_list and re.search(r"\bcount\s*\(", normalized):
            self.errors.append("کاربر لیست/اطلاعات خواسته اما SQL خروجی شمارشی COUNT ساخته است")
            ok = False

        if intent.requested_entity == "student" and intent.province:
            required = {"students", "schools", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("برای فیلتر استان دانش‌آموز باید مسیر students -> schools -> organization_units استفاده شود")
                ok = False
            if not self._has_join(sql, "students", "school_id", "schools", "id"):
                self.errors.append("JOIN ضروری students.school_id = schools.id وجود ندارد")
                ok = False
            if not self._has_join(sql, "schools", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN ضروری schools.organization_unit_id = organization_units.id وجود ندارد")
                ok = False
            if not re.search(r"\borganization_units\.province\b", normalized):
                self.errors.append("فیلتر استان دانش‌آموز باید روی organization_units.province باشد")
                ok = False

        if intent.requested_entity == "student" and intent.city:
            required = {"students", "schools", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("Student city filters must use students -> schools -> organization_units")
                ok = False
            if not self._has_join(sql, "students", "school_id", "schools", "id"):
                self.errors.append("JOIN required: students.school_id = schools.id")
                ok = False
            if not self._has_join(sql, "schools", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN required: schools.organization_unit_id = organization_units.id")
                ok = False
            if not re.search(r"\borganization_units\.city\b", normalized):
                self.errors.append("Student city filters must use organization_units.city")
                ok = False

        if intent.requested_entity == "student" and intent.named_school:
            required = {"students", "schools"}
            if not required.issubset(tables):
                self.errors.append("برای دانش‌آموزان یک مدرسه باید students به schools وصل شود")
                ok = False
            if not self._has_join(sql, "students", "school_id", "schools", "id"):
                self.errors.append("JOIN ضروری students.school_id = schools.id وجود ندارد")
                ok = False
            if not re.search(r"\bschools\.name\b", normalized):
                self.errors.append("فیلتر نام مدرسه باید روی schools.name باشد")
                ok = False

        if intent.requested_entity == "school" and intent.province:
            required = {"schools", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("برای فیلتر استان مدرسه باید schools به organization_units وصل شود")
                ok = False
            if not self._has_join(sql, "schools", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN ضروری schools.organization_unit_id = organization_units.id وجود ندارد")
                ok = False
            if intent.aggregation == "COUNT" and not re.search(r"\bcount\s*\(\s*(?:distinct\s+)?schools\.id\s*\)", normalized):
                self.errors.append("برای تعداد مدارس باید schools.id شمارش شود")
                ok = False

        if intent.requested_entity == "school" and intent.city:
            required = {"schools", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("برای فیلتر شهر مدرسه باید schools به organization_units وصل شود")
                ok = False
            if not self._has_join(sql, "schools", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN ضروری schools.organization_unit_id = organization_units.id وجود ندارد")
                ok = False
            if "organization_units.city" not in normalized:
                self.errors.append("فیلتر شهر مدرسه باید روی organization_units.city باشد")
                ok = False

        if intent.requested_entity == "employee" and intent.province:
            required = {"employees", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("برای فیلتر استان کارمند باید employees به organization_units وصل شود")
                ok = False
            if not self._has_join(sql, "employees", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN ضروری employees.organization_unit_id = organization_units.id وجود ندارد")
                ok = False
            if not re.search(r"\b(?:organization_units|ou)\.province\b", normalized):
                self.errors.append("فیلتر استان کارمند باید روی organization_units.province باشد")
                ok = False

        if intent.requested_entity == "employee" and intent.city:
            required = {"employees", "organization_units"}
            if not required.issubset(tables):
                self.errors.append("Employee city filters must join employees to organization_units")
                ok = False
            if not self._has_join(sql, "employees", "organization_unit_id", "organization_units", "id"):
                self.errors.append("JOIN required: employees.organization_unit_id = organization_units.id")
                ok = False
            if not re.search(r"\b(?:organization_units|ou)\.city\b", normalized):
                self.errors.append("Employee city filters must use organization_units.city")
                ok = False

        if intent.requested_entity == "employee" and intent.wants_service_years:
            if "retirement_records" not in tables:
                self.errors.append("برای سنوات کارمند باید جدول retirement_records استفاده شود")
                ok = False
            if "retirement_records.pension_amount" not in normalized:
                self.errors.append("کاربر سنوات را خواسته اما ستون retirement_records.pension_amount در SQL نیست")
                ok = False
            if not self._has_join(sql, "retirement_records", "employee_id", "employees", "id"):
                self.errors.append("JOIN ضروری retirement_records.employee_id = employees.id وجود ندارد")
                ok = False

        if intent.requested_entity == "retirement" and getattr(intent, "ranking_metric", None) == "pension_amount":
            required = {"employees", "retirement_records"}
            if not required.issubset(tables):
                self.errors.append("Pension ranking must use employees and retirement_records")
                ok = False
            if "retirement_records.pension_amount" not in normalized:
                self.errors.append("Pension ranking must use retirement_records.pension_amount")
                ok = False
            if "order by" not in normalized or "limit 1" not in normalized:
                self.errors.append("Pension ranking must order by pension_amount and limit to one row")
                ok = False
            if not self._has_join(sql, "retirement_records", "employee_id", "employees", "id"):
                self.errors.append("JOIN required: retirement_records.employee_id = employees.id")
                ok = False

        if intent.requested_entity == "school" and intent.wants_phone:
            if "schools.phone" not in normalized:
                self.errors.append("کاربر شماره تلفن مدرسه را خواسته اما ستون schools.phone در خروجی نیست")
                ok = False

        if intent.requested_columns:
            aliases = self._aliases(sql)
            qualified = {(aliases.get(table, table), column) for table, column in self._qualified_columns(sql)}
            expected_table = self._expected_table_for_entity(intent.requested_entity)
            if expected_table:
                for column in intent.requested_columns:
                    if (expected_table, column.lower()) not in qualified:
                        self.errors.append(f"ستون درخواستی کاربر در SQL وجود ندارد: {expected_table}.{column}")
                        ok = False

        return ok

    def validate(
        self,
        sql: str,
        schema: DatabaseSchema,
        report: Optional[Report] = None,
        intent: Optional[QueryIntent] = None,
    ) -> ValidationResult:
        self.errors = []
        self.warnings = []

        if not sql or not sql.strip():
            self.errors.append("SQL خالی است")
        else:
            self.validate_select_only(sql)
            self.validate_table_whitelist(sql, schema, report)
            self.validate_columns(sql, schema)
            self.validate_syntax(sql)
            self.validate_complexity(sql)
            self.validate_constraints(sql, intent)
            self.validate_semantic_rules(sql, intent)

        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings,
        )

    def _tables(self, sql: str) -> list[str]:
        identifier = self.IDENTIFIER
        return [
            (match.group(1) or match.group(2)).lower()
            for match in re.finditer(rf"\bFROM\s+({identifier})|\bJOIN\s+({identifier})", sql, re.I)
        ]

    def _aliases(self, sql: str) -> dict[str, str]:
        aliases = {}
        identifier = self.IDENTIFIER
        for match in re.finditer(
            rf"\b(?:FROM|JOIN)\s+({identifier})(?:\s+(?:AS\s+)?({identifier}))?",
            sql,
            re.I,
        ):
            table = match.group(1).lower()
            alias = (match.group(2) or "").lower()
            if alias and alias not in {"on", "where", "join", "group", "order", "limit"}:
                aliases[alias] = table
        return aliases

    def _qualified_columns(self, sql: str) -> list[tuple[str, str]]:
        identifier = self.IDENTIFIER
        return [
            (match.group(1).lower(), match.group(2).lower())
            for match in re.finditer(rf"\b({identifier})\.({identifier})\b", sql, re.I)
        ]

    def _has_join(self, sql: str, left_table: str, left_column: str, right_table: str, right_column: str) -> bool:
        aliases = self._aliases(sql)
        normalized_pairs = {
            (aliases.get(table, table), column)
            for table, column in self._qualified_columns(sql)
        }
        return (
            (left_table, left_column) in normalized_pairs
            and (right_table, right_column) in normalized_pairs
        )

    def _expected_table_for_entity(self, entity: Optional[str]) -> Optional[str]:
        return {
            "employee": "employees",
            "student": "students",
            "school": "schools",
            "organization": "organization_units",
            "salary": "salary_items",
            "ranking": "ranking_requests",
            "retirement": "retirement_records",
        }.get(entity)


sql_validator = SQLValidator()
