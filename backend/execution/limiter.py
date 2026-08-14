import re

from backend.sql.models import ValidationResult


class SQLLimiter:
    MAX_LIMIT = 1000
    MAX_ROWS = 1000
    MAX_TIMEOUT_SECONDS = 30
    MAX_JOINS = 4
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

    def validate_for_execution(
        self,
        sql: str,
        timeout: int | None = None,
        max_rows: int | None = None,
    ) -> ValidationResult:
        errors = []

        normalized = re.sub(r"\s+", " ", sql).strip()
        sql_upper = normalized.upper()
        sql_lower = normalized.lower()

        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", sql_upper):
                errors.append(f"Query {keyword} is not allowed; only SELECT queries are allowed")

        if not sql_upper.startswith("SELECT"):
            errors.append("Only SELECT queries are allowed")

        if ";" in sql.strip()[:-1]:
            errors.append("Multiple SQL statements are not allowed")

        if re.search(r"^\s*select\s+\*", sql_lower):
            errors.append("SELECT * is not allowed for execution; request explicit columns")

        limit_match = re.search(r"\blimit\s+(\d+)\b", sql_lower)
        if limit_match and int(limit_match.group(1)) > self.MAX_LIMIT:
            errors.append(f"LIMIT cannot be greater than {self.MAX_LIMIT}")

        if max_rows is not None and max_rows > self.MAX_ROWS:
            errors.append(f"max_rows cannot be greater than {self.MAX_ROWS}")

        if timeout is not None and timeout > self.MAX_TIMEOUT_SECONDS:
            errors.append(f"timeout cannot be greater than {self.MAX_TIMEOUT_SECONDS} seconds")

        join_count = len(re.findall(r"\bjoin\b", sql_lower))
        if join_count > self.MAX_JOINS:
            errors.append(f"query cannot use more than {self.MAX_JOINS} JOINs")

        has_where = bool(re.search(r"\bwhere\b", sql_lower))
        has_limit = bool(limit_match)
        is_aggregate_or_grouped = bool(
            re.search(r"\b(count|sum|avg|min|max)\s*\(", sql_lower)
            or re.search(r"\bgroup\s+by\b", sql_lower)
        )
        if join_count >= 2 and not has_where and not has_limit and not is_aggregate_or_grouped:
            errors.append("multi-table list queries must include a WHERE filter or safe LIMIT")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )


sql_limiter = SQLLimiter()
