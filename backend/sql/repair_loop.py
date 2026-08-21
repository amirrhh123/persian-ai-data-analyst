"""Bounded, deterministic repair loop for generated read-only SQL."""

from __future__ import annotations

import re
from typing import Optional

from backend.database.models import DatabaseSchema
from backend.knowledge.models import Report
from backend.pipeline.intent import QueryIntent
from backend.sql.identifier_canonicalizer import canonicalize_sql_identifiers
from backend.sql.models import SQLRepairAttempt, SQLRepairResult
from backend.sql.validator import SQLValidator


class SQLRepairLoop:
    """Apply only schema-grounded repairs and revalidate after each attempt."""

    def __init__(self, maximum_attempts: int = 2) -> None:
        if maximum_attempts < 1 or maximum_attempts > 5:
            raise ValueError("maximum_attempts must be between 1 and 5")
        self.maximum_attempts = maximum_attempts

    @staticmethod
    def _contains_forbidden_sql(sql: str) -> bool:
        return any(
            re.search(rf"\b{keyword}\b", sql, re.IGNORECASE)
            for keyword in SQLValidator.FORBIDDEN_KEYWORDS
        )

    @staticmethod
    def _strip_markdown(sql: str) -> tuple[str, bool]:
        match = re.fullmatch(r"\s*```(?:sql)?\s*(.*?)\s*```\s*", sql, re.I | re.S)
        return (match.group(1).strip(), True) if match else (sql, False)

    @staticmethod
    def _cap_limit(sql: str) -> tuple[str, bool]:
        updated = re.sub(
            r"\bLIMIT\s+(\d+)\b",
            lambda match: "LIMIT 1000" if int(match.group(1)) > 1000 else match.group(0),
            sql,
            flags=re.IGNORECASE,
        )
        return updated, updated != sql

    @staticmethod
    def _quote_national_id(sql: str) -> tuple[str, bool]:
        updated = re.sub(
            r"(\b(?:[a-z_][a-z0-9_]*\.)?national_id\s*=\s*)([0-9۰-۹]{10})(?![0-9۰-۹'])",
            r"\1'\2'",
            sql,
            flags=re.IGNORECASE,
        )
        return updated, updated != sql

    @staticmethod
    def _normalize_postgres_identifier_quotes(sql: str) -> tuple[str, bool]:
        updated = re.sub(
            r"`([^`]+)`",
            lambda match: '"' + match.group(1).replace('"', '""') + '"',
            sql,
        )
        return updated, updated != sql

    @staticmethod
    def _expand_select_star(sql: str, schema: DatabaseSchema) -> tuple[str, bool]:
        if not re.search(r"^\s*SELECT\s+\*\s+FROM\b", sql, re.IGNORECASE):
            return sql, False
        table_match = re.search(
            r"\bFROM\s+([a-z_][a-z0-9_]*)(?:\s+(?:AS\s+)?([a-z_][a-z0-9_]*))?",
            sql,
            re.IGNORECASE,
        )
        if not table_match:
            return sql, False
        table_name = table_match.group(1)
        alias = table_match.group(2)
        if alias and alias.lower() in {"where", "join", "group", "order", "limit"}:
            alias = None
        table = next((item for item in schema.tables if item.name.lower() == table_name.lower()), None)
        if not table or not table.columns:
            return sql, False
        qualifier = alias or table.name
        columns = ", ".join(f"{qualifier}.{column.name}" for column in table.columns)
        updated = re.sub(r"^\s*SELECT\s+\*", f"SELECT {columns}", sql, count=1, flags=re.I)
        return updated, updated != sql

    @staticmethod
    def _add_safe_limit(sql: str) -> tuple[str, bool]:
        normalized = sql.lower()
        joins = len(re.findall(r"\bjoin\b", normalized))
        unsafe_list = (
            joins >= 2
            and not re.search(r"\bwhere\b", normalized)
            and not re.search(r"\blimit\s+\d+\b", normalized)
            and not re.search(r"\b(count|sum|avg|min|max)\s*\(|\bgroup\s+by\b", normalized)
        )
        if not unsafe_list:
            return sql, False
        stripped = sql.rstrip().rstrip(";")
        return f"{stripped} LIMIT 1000", True

    def _repair_once(self, sql: str, schema: DatabaseSchema) -> tuple[str, list[str]]:
        updated = sql
        strategies: list[str] = []

        def canonicalize(value: str) -> tuple[str, bool]:
            repaired, report = canonicalize_sql_identifiers(value, schema)
            return repaired, report["changed"]

        for name, operation in (
            ("strip_markdown", lambda value: self._strip_markdown(value)),
            ("normalize_postgres_identifier_quotes", lambda value: self._normalize_postgres_identifier_quotes(value)),
            ("canonicalize_identifiers", canonicalize),
            ("expand_select_star", lambda value: self._expand_select_star(value, schema)),
            ("quote_national_id", lambda value: self._quote_national_id(value)),
            ("cap_limit", lambda value: self._cap_limit(value)),
            ("add_safe_limit", lambda value: self._add_safe_limit(value)),
        ):
            updated, changed = operation(updated)
            if changed:
                strategies.append(name)
        return updated, strategies

    def repair(
        self,
        sql: str,
        schema: DatabaseSchema,
        report: Optional[Report] = None,
        intent: Optional[QueryIntent] = None,
    ) -> SQLRepairResult:
        """Repair, validate, and stop on success, no progress, or policy rejection."""
        validator = SQLValidator()
        initial_validation = validator.validate(sql, schema, report=report, intent=intent)
        if initial_validation.is_valid:
            return SQLRepairResult(
                sql=sql, valid=True, stopped_reason="already_valid",
                validation=initial_validation,
            )
        if self._contains_forbidden_sql(sql):
            return SQLRepairResult(
                sql=sql, valid=False, stopped_reason="forbidden_statement",
                validation=initial_validation,
            )

        current = sql
        attempts: list[SQLRepairAttempt] = []
        final_validation = initial_validation
        for attempt_number in range(1, self.maximum_attempts + 1):
            candidate, strategies = self._repair_once(current, schema)
            if not strategies or candidate == current:
                return SQLRepairResult(
                    sql=current,
                    repaired=bool(attempts),
                    valid=False,
                    stopped_reason="no_safe_repair",
                    attempts=attempts,
                    validation=final_validation,
                )
            final_validation = SQLValidator().validate(
                candidate, schema, report=report, intent=intent,
            )
            attempts.append(SQLRepairAttempt(
                attempt=attempt_number,
                sql=candidate,
                strategies=strategies,
                validation=final_validation,
            ))
            current = candidate
            if final_validation.is_valid:
                return SQLRepairResult(
                    sql=current,
                    repaired=True,
                    valid=True,
                    stopped_reason="validated",
                    attempts=attempts,
                    validation=final_validation,
                )

        return SQLRepairResult(
            sql=current,
            repaired=bool(attempts),
            valid=False,
            stopped_reason="attempt_limit",
            attempts=attempts,
            validation=final_validation,
        )


sql_repair_loop = SQLRepairLoop()
