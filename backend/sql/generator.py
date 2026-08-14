from typing import Optional

from backend.database.models import DatabaseSchema
from backend.config import get_settings
from backend.knowledge.models import Report
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog
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
    ) -> str:
        allowed_tables = set(plan.required_tables)
        schema_lines = []
        for table in schema.tables:
            if table.name in allowed_tables:
                columns = ", ".join(col.name for col in table.columns)
                schema_lines.append(f"- {table.name}: {columns}")

        semantic_lines = []
        if semantic_catalog:
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
    ) -> GeneratedSQL:
        template = self._template_sql(plan)
        if template:
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

        semantic_catalog = load_tenant_semantic_catalog(tenant_id)
        prompt = self._build_prompt(plan, schema, business_rules, report, semantic_catalog=semantic_catalog)
        system_prompt = (
            "You are a strict SQL generator. Return only JSON with sql, explanation, confidence. "
            "Never return raw SQL or Markdown. Use only approved schema identifiers."
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

    def _template_sql(self, plan: SQLPlan) -> Optional[str]:
        return render_template_sql(plan)


sql_generator = SQLGenerator()
