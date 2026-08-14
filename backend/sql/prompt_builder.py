from typing import List, Optional
from backend.database.models import DatabaseSchema, TableInfo, RelationshipInfo
from backend.sql.models import SQLPlan
from backend.knowledge.models import Report, SQLHint


class PromptBuilder:
    def build_schema_context(self, schema: DatabaseSchema, tables: List[str] = None) -> str:
        context = "ساختار دیتابیس:\n\n"
        
        for table in schema.tables:
            if tables and table.name not in tables:
                continue
            
            context += f"جدول {table.name}:\n"
            for col in table.columns:
                pk = " (کلید اصلی)" if col.is_primary_key else ""
                nullable = "قابل null" if col.is_nullable else "غیرقابل null"
                context += f"  - {col.name}: {col.data_type} ({nullable}){pk}\n"
            context += "\n"
        
        return context
    
    def build_relationships_context(self, schema: DatabaseSchema) -> str:
        if not schema.relationships:
            return ""
        
        context = "اتصالات جداول:\n"
        for rel in schema.relationships:
            context += f"  - {rel.source_table}.{rel.source_column} → {rel.target_table}.{rel.target_column}\n"
        
        return context
    
    def build_plan_context(self, plan: SQLPlan) -> str:
        context = "نقشه SQL:\n"
        context += f"  جداول: {', '.join(plan.required_tables)}\n"
        context += f"  ستون‌ها: {', '.join(plan.selected_columns)}\n"
        
        if plan.joins:
            context += "  اتصالات:\n"
            for join in plan.joins:
                context += f"    - {join['from_table']}.{join['from_column']} = {join['to_table']}.{join['to_column']}\n"
        
        if plan.filters:
            context += "  فیلترها:\n"
            for f in plan.filters:
                context += f"    - {f['column']} {f['operator']} {f['value']}\n"
        
        return context
    
    def build_report_context(self, report: Report) -> str:
        context = f"گزارش: {report.name}\n"
        context += f"توضیحات: {report.description}\n"
        context += f"جدول اصلی: {report.linked_table}\n\n"
        
        if report.important_columns:
            context += "ستون‌های مهم:\n"
            for col_name, col_def in report.important_columns.items():
                context += f"  - {col_name}: {col_def.meaning}"
                if col_def.persian_name:
                    context += f" ({col_def.persian_name})"
                context += "\n"
            context += "\n"
        
        if report.sql_hints:
            hints = report.sql_hints
            if hints.default_filters:
                context += "فیلترهای پیش‌فرض:\n"
                for f in hints.default_filters:
                    context += f"  - {f}\n"
            
            if hints.preferred_joins:
                context += "اتصالات ترجیحی:\n"
                for j in hints.preferred_joins:
                    context += f"  - {j}\n"
            
            if hints.group_by_columns:
                context += "ستون‌های گروه‌بندی:\n"
                for c in hints.group_by_columns:
                    context += f"  - {c}\n"
        
        return context
    
    def build_full_prompt(
        self,
        question: str,
        plan: SQLPlan,
        schema: DatabaseSchema,
        business_rules: str = "",
        report: Optional[Report] = None
    ) -> str:
        schema_context = self.build_schema_context(schema, plan.required_tables)
        relationships_context = self.build_relationships_context(schema)
        plan_context = self.build_plan_context(plan)
        
        report_context = ""
        if report:
            report_context = self.build_report_context(report)
        
        prompt = f"""سوال کاربر: {question}

{report_context}

{plan_context}

{schema_context}

{relationships_context}

{business_rules}

یک کوئری SQL SELECT بنویس که سوال کاربر را پاسخ دهد.
فقط کوئری SELECT بنویس.
از نام جداول و ستون‌های واقعی استفاده کن.
از فیلترهای پیش‌فرض و اتصالات ترجیحی استفاده کن.

خروجی را به صورت JSON برگردان:
{{
  "sql": "SELECT ...",
  "explanation": "توضیح به فارسی",
  "confidence": 0.8
}}"""
        
        return prompt


prompt_builder = PromptBuilder()
