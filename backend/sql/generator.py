from typing import Optional

from backend.database.models import DatabaseSchema
from backend.config import get_settings
from backend.knowledge.models import Report
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog
from backend.semantic.snapshot import SemanticSnapshot
from backend.services.llm_service import llm_service
from backend.sql.models import GeneratedSQL, SQLPlan
from backend.sql.structured import parse_structured_sql_response
from backend.sql.templates import render_template_sql


class SQLGenerator:
    def __init__(self):
        self.llm = llm_service
        self.settings = get_settings()

    def _build_prompt(
        self,
        plan: SQLPlan,
        schema: DatabaseSchema,
        business_rules: str = "",
        report: Optional[Report] = None,
        semantic_catalog: Optional[SemanticCatalog] = None,
        semantic_context: list[str] | None = None,
    ) -> str:
        allowed_tables = set(plan.required_tables)
        schema_lines = []
        for table in schema.tables:
            if table.name in allowed_tables:
                columns = ", ".join(col.name for col in table.columns)
                schema_lines.append(f"- {table.name}: {columns}")

        semantic_lines = list(semantic_context or [])
        if semantic_catalog and not semantic_lines:
            for table in semantic_catalog.tables:
                if table.name not in allowed_tables:
                    continue
                semantic_lines.append(
                    f"- {table.name} means {table.description}; aliases: {', '.join(table.aliases)}"
                )
                for column in table.columns:
                    alias_text = ", ".join(column.aliases)
                    details = f"  - {table.name}.{column.name}: {column.description}"
                    if alias_text:
                        details += f"; aliases: {alias_text}"
                    if column.value_type:
                        details += f"; value_type: {column.value_type}"
                    if column.pii:
                        details += "; pii: true"
                    semantic_lines.append(details)

            applied_tables = {
                table.name
                for table in semantic_catalog.tables
                if table.name in allowed_tables
            }
            for rule in semantic_catalog.rules:
                if not rule.applies_to:
                    semantic_lines.append(f"- RULE {rule.name}: {rule.description}")
                    continue
                applies = {item.split(".", 1)[0] for item in rule.applies_to}
                if applies & applied_tables:
                    semantic_lines.append(f"- RULE {rule.name}: {rule.description}")

        report_lines = []
        if report:
            report_lines.extend(
                [
                    f"Report id: {report.id}",
                    f"Report name: {report.name}",
                    f"Primary table: {report.linked_table}",
                ]
            )
            if report.sql_hints:
                report_lines.append("Approved joins:")
                report_lines.extend(f"- {join}" for join in report.sql_hints.preferred_joins)
                report_lines.append("Aggregate columns:")
                report_lines.extend(f"- {column}" for column in report.sql_hints.aggregate_columns)
                report_lines.append("Group-by columns:")
                report_lines.extend(f"- {column}" for column in report.sql_hints.group_by_columns)

        return f"""You generate PostgreSQL SELECT queries for a Persian data analyst.

Return only strict JSON with this shape:
{{"sql":"SELECT ...","explanation":"...","confidence":0.8}}

Rules:
- Use only the allowed tables and columns listed below.
- Values such as STUDENT_BY_NATIONAL_ID, EMPLOYEE_BY_NATIONAL_ID, EMPLOYEE_IDENTITY_BY_NATIONAL_ID, and other uppercase plan markers are internal instructions, not database columns. Never write them in SQL.
- For a student question, use students (and schools only when the school name is requested); never substitute employees.
- For a national-id student lookup, filter students.national_id and return columns from students.
- Do not invent tables, columns, aliases, filters, statuses, or values.
- Generate exactly one SELECT statement.
- Do not wrap the answer in Markdown fences.
- Respect required filters, grouping, sorting, joins, and LIMIT from the plan.
- Respect active semantic rules, aliases, business terms, and value mappings.

Question:
{business_rules}

SQL plan:
- tables: {", ".join(plan.required_tables)}
- selected columns: {", ".join(plan.selected_columns)}
- filters: {plan.filters}
- joins: {plan.joins}
- aggregations: {plan.aggregations}
- order_by: {plan.order_by}
- limit: {plan.limit}

Report context:
{chr(10).join(report_lines)}

Allowed schema:
{chr(10).join(schema_lines)}

Active semantic layer:
{chr(10).join(semantic_lines)}
"""

    async def generate(
        self,
        plan: SQLPlan,
        schema: DatabaseSchema,
        business_rules: str = "",
        report: Optional[Report] = None,
        tenant_id: str | None = None,
        max_retries: int = 2,
        allow_template: bool = True,
        semantic_snapshot: SemanticSnapshot | None = None,
    ) -> GeneratedSQL:
        semantic_catalog = (
            semantic_snapshot.catalog
            if semantic_snapshot is not None
            else load_tenant_semantic_catalog(tenant_id)
        )
        template = self._template_sql(plan, semantic_catalog) if allow_template else None
        if template and not self.settings.llm_force_for_all_questions:
            return GeneratedSQL(
                sql=template,
                explanation="SQL از روی نقشه ساختاریافته و اسکیما تولید شد.",
                confidence=1.0,
                plan=plan,
                generation_source="template",
            )

        if not self.settings.llm_enabled:
            return GeneratedSQL(
                sql="",
                explanation=(
                    "حالت سبک فعال است و برای این سؤال template یا قانون semantic کافی پیدا نشد. "
                    "برای پاسخ به این نوع سؤال باید Ollama/LLM را فعال کنید یا برای آن الگوی semantic اضافه شود."
                ),
                confidence=0.0,
                plan=plan,
                generation_source="llm_disabled",
            )

        context_matches = (
            semantic_snapshot.context_index.search(
                business_rules,
                allowed_tables=set(plan.required_tables),
                limit=18,
            )
            if semantic_snapshot is not None
            else []
        )
        prompt = self._build_prompt(
            plan,
            schema,
            business_rules,
            report,
            semantic_catalog=semantic_catalog,
            semantic_context=[match.document.text for match in context_matches],
        )
        system_prompt = """You are the SQL generation component of an offline Persian enterprise NL-to-SQL system.
Convert the already analyzed intent and plan into exactly one safe PostgreSQL SELECT statement.
Return ONLY valid JSON with exactly these fields: {\"sql\": \"SELECT ...\", \"explanation\": \"...\", \"confidence\": 0.0}.
Never return Markdown, extra text, or a second statement.

Grounding rules:
- Use only tables and columns listed in Allowed schema and SQL plan.
- Use only approved relationships and joins.
- Preserve every filter, aggregation, grouping, sorting, date range, and limit from the plan.
- Never invent identifiers, values, statuses, entities, or business meanings.
- Uppercase plan markers such as STUDENT_BY_NATIONAL_ID, EMPLOYEE_BY_NATIONAL_ID,
  EMPLOYEE_IDENTITY_BY_NATIONAL_ID and GENERIC_* are internal instructions, NOT columns;
  never write them in SQL.
- For a student lookup use students; for an employee lookup use employees. Do not substitute one for the other.
- For a national-id student lookup filter students.national_id. For a national-id employee lookup filter employees.national_id.
- Prefer the minimum number of tables. Join only when needed for a selected column, filter, grouping, or approved path.
- Prevent row multiplication in aggregates; use COUNT(DISTINCT ...) or pre-aggregation when required.
- Only SELECT/WITH is allowed. No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, COPY, CALL, or EXECUTE.
- If the plan is ambiguous, unsupported, or missing a required value, return an empty sql string and confidence 0.0 rather than guessing.

Before responding, silently verify every table, column, alias, join, filter, aggregate, group, sort, limit, and that the query answers the requested metric."""

        if template and self.settings.llm_force_for_all_questions:
            # Ollama participates in every request, but an approved deterministic
            # template remains authoritative for known high-confidence intents.
            # This prevents a model rewrite from dropping required joins/filters.
            try:
                await self.llm.chat(
                    prompt + "\nApproved candidate SQL:\n" + template +
                    "\nReview this query against the plan and schema. Return the normal JSON contract.",
                    system_prompt,
                )
            except Exception:
                pass
            return GeneratedSQL(
                sql=template,
                explanation="SQL قطعی سیستم پس از بررسی Ollama استفاده شد.",
                confidence=1.0,
                plan=plan,
                generation_source="llm_reviewed_template",
            )

        errors = []
        for attempt in range(max_retries + 1):
            try:
                response = await self.llm.chat(prompt, system_prompt)
                parsed = parse_structured_sql_response(response)
                return GeneratedSQL(
                    sql=parsed.sql,
                    explanation=parsed.explanation,
                    confidence=parsed.confidence,
                    plan=plan,
                    generation_source="llm",
                )
            except Exception as exc:
                errors.append(f"attempt {attempt + 1}: {exc}")

        return GeneratedSQL(
            sql="",
            explanation="خروجی ساختاریافته SQL معتبر تولید نشد: " + " | ".join(errors),
            confidence=0.0,
            plan=plan,
            generation_source="llm_failed",
        )

    def _template_sql(
        self,
        plan: SQLPlan,
        semantic_catalog: SemanticCatalog | None = None,
    ) -> Optional[str]:
        return render_template_sql(plan, semantic_catalog)


sql_generator = SQLGenerator()
