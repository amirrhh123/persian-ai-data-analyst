import re
from typing import Any

from backend.database.models import DatabaseSchema
from backend.semantic.models import normalize_identifier


_IDENTIFIER_CHARS = "A-Za-z0-9_۰-۹٠-٩"
_TABLE_REF_PATTERN = re.compile(
    rf"\b(?:FROM|JOIN)\s+([{_IDENTIFIER_CHARS}]+)",
    flags=re.IGNORECASE,
)


def canonicalize_sql_identifiers(sql: str, schema: DatabaseSchema) -> tuple[str, dict[str, Any]]:
    """Repair safe table-name drift in generated SQL.

    The LLM can occasionally turn a real table such as ``test1`` into ``test``.
    We only rewrite that when the schema has exactly one table whose normalized
    name is the unknown token plus a numeric suffix. Ambiguous matches are left
    untouched so the normal validator can reject them.
    """

    schema_table_names = [table.name for table in schema.tables]
    schema_table_norms = {normalize_identifier(table_name) for table_name in schema_table_names}
    replacements: dict[str, str] = {}

    for match in _TABLE_REF_PATTERN.finditer(sql):
        raw_table = match.group(1)
        normalized_table = normalize_identifier(raw_table)
        if normalized_table in schema_table_norms:
            continue
        canonical = _unique_numeric_suffix_table_match(normalized_table, schema_table_names)
        if canonical:
            replacements[raw_table] = canonical

    if not replacements:
        return sql, {"changed": False, "replacements": {}}

    updated_sql = sql
    for raw_table, canonical_table in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        escaped = re.escape(raw_table)
        updated_sql = re.sub(
            rf"(\b(?:FROM|JOIN)\s+){escaped}(?=$|[\s,;])",
            rf"\1{canonical_table}",
            updated_sql,
            flags=re.IGNORECASE,
        )
        updated_sql = re.sub(
            rf"(?<![{_IDENTIFIER_CHARS}]){escaped}(?=\.)",
            canonical_table,
            updated_sql,
        )

    return updated_sql, {"changed": updated_sql != sql, "replacements": replacements}


def _unique_numeric_suffix_table_match(unknown_table: str, schema_table_names: list[str]) -> str | None:
    if not unknown_table:
        return None

    matches: list[str] = []
    for table_name in schema_table_names:
        normalized_table = normalize_identifier(table_name)
        if not normalized_table.startswith(unknown_table):
            continue
        suffix = normalized_table[len(unknown_table) :]
        if suffix and suffix.isdigit():
            matches.append(table_name)

    return matches[0] if len(matches) == 1 else None
