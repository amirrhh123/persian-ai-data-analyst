from typing import Dict
from backend.knowledge.models import CompanyContext, ReportContext, Report, ReportColumnDefinition, SQLHint


class ContextBuilder:
    def __init__(self, context: CompanyContext):
        self.context = context
    
    def build_company_context(self) -> str:
        if not self.context.company:
            return ""
        
        company = self.context.company
        lines = [f"نام شرکت: {company.name}"]
        lines.append(f"صنعت: {company.industry}")
        
        if company.description:
            lines.append(f"توضیحات: {company.description}")
        
        if company.locations:
            lines.append(f"مکان‌ها: {', '.join(company.locations)}")
        
        if company.departments:
            lines.append(f"بخش‌ها: {', '.join(company.departments)}")
        
        return "\n".join(lines)
    
    def build_definitions_context(self) -> str:
        if not self.context.definitions:
            return ""
        
        lines = ["تعریف‌های کسب‌وکار:"]
        for defn in self.context.definitions:
            lines.append(f"- {defn.term}: {defn.definition}")
        
        return "\n".join(lines)
    
    def build_metrics_context(self) -> str:
        if not self.context.metrics:
            return ""
        
        lines = ["شاخص‌های کلیدی عملکرد:"]
        for metric in self.context.metrics:
            lines.append(f"- {metric.name}: {metric.formula}")
            if metric.target:
                lines.append(f"  هدف: {metric.target}")
        
        return "\n".join(lines)
    
    def build_rules_context(self) -> str:
        if not self.context.rules:
            return ""
        
        lines = ["قوانین کسب‌وکار:"]
        for rule in self.context.rules:
            lines.append(f"- {rule.name}: {rule.description}")
            if rule.condition:
                lines.append(f"  شرط: {rule.condition}")
            if rule.action:
                lines.append(f"  عمل: {rule.action}")
        
        return "\n".join(lines)
    
    def build_terminology_context(self) -> str:
        if not self.context.terminology:
            return ""
        
        lines = ["اصطلاحات تخصصی:"]
        for term in self.context.terminology:
            lines.append(f"- {term.term}: {term.meaning}")
            if term.synonyms:
                lines.append(f"  مترادف‌ها: {', '.join(term.synonyms)}")
        
        return "\n".join(lines)
    
    def build_full_context(self) -> str:
        sections = [
            self.build_company_context(),
            self.build_definitions_context(),
            self.build_metrics_context(),
            self.build_rules_context(),
            self.build_terminology_context()
        ]
        
        return "\n\n".join(filter(None, sections))
    
    def build_structured_context(self) -> dict:
        return {
            "company_context": self.build_company_context(),
            "definitions": self.build_definitions_context(),
            "metrics": self.build_metrics_context(),
            "rules": self.build_rules_context(),
            "terminology": self.build_terminology_context()
        }


class ReportContextBuilder:
    def __init__(self, report_context: ReportContext):
        self.context = report_context
    
    def build_report_info(self) -> str:
        report = self.context.report
        lines = [f"نام گزارش: {report.name}"]
        lines.append(f"توضیحات: {report.description}")
        lines.append(f"جدول مرتبط: {report.linked_table}")
        return "\n".join(lines)
    
    def build_metrics_context(self) -> str:
        if not self.context.metrics:
            return ""
        
        lines = ["شاخص‌های مجاز این گزارش:"]
        for metric in self.context.metrics:
            lines.append(f"- {metric.name}: {metric.formula}")
            if metric.unit:
                lines.append(f"  واحد: {metric.unit}")
            if metric.target:
                lines.append(f"  هدف: {metric.target}")
        
        return "\n".join(lines)
    
    def build_rules_context(self) -> str:
        if not self.context.rules:
            return ""
        
        lines = ["قوانین مرتبط:"]
        for rule in self.context.rules:
            lines.append(f"- {rule.name}: {rule.description}")
            if hasattr(rule, 'sql_note') and rule.sql_note:
                lines.append(f"  نکته SQL: {rule.sql_note}")
        
        return "\n".join(lines)
    
    def build_examples_context(self) -> str:
        if not self.context.report.example_questions:
            return ""
        
        lines = ["نمونه سوالات:"]
        for q in self.context.report.example_questions:
            lines.append(f"- {q}")
        
        return "\n".join(lines)
    
    def build_columns_context(self) -> str:
        if not self.context.report.important_columns:
            return ""
        
        lines = ["ستون‌های مهم جدول:"]
        for col_name, col_def in self.context.report.important_columns.items():
            lines.append(f"- {col_name}: {col_def.meaning}")
            if col_def.persian_name:
                lines.append(f"  نام فارسی: {col_def.persian_name}")
        
        return "\n".join(lines)
    
    def build_sql_hints_context(self) -> str:
        hints = self.context.report.sql_hints
        if not hints:
            return ""
        
        lines = ["نکات SQL:"]
        
        if hints.default_filters:
            lines.append("  فیلترهای پیش‌فرض:")
            for f in hints.default_filters:
                lines.append(f"    - {f}")
        
        if hints.preferred_joins:
            lines.append("  اتصالات ترجیحی:")
            for j in hints.preferred_joins:
                lines.append(f"    - {j}")
        
        if hints.aggregate_columns:
            lines.append("  ستون‌های تجمیعی:")
            for c in hints.aggregate_columns:
                lines.append(f"    - {c}")
        
        if hints.group_by_columns:
            lines.append("  گروه‌بندی بر اساس:")
            for c in hints.group_by_columns:
                lines.append(f"    - {c}")
        
        return "\n".join(lines)
    
    def build_full_context(self) -> str:
        sections = [
            self.build_report_info(),
            self.build_columns_context(),
            self.build_metrics_context(),
            self.build_rules_context(),
            self.build_sql_hints_context(),
            self.build_examples_context()
        ]
        
        return "\n\n".join(filter(None, sections))
    
    def build_structured_context(self) -> dict:
        return {
            "report_name": self.context.report.name,
            "table": self.context.report.linked_table,
            "columns": self.build_columns_context(),
            "metrics": self.build_metrics_context(),
            "rules": self.build_rules_context(),
            "sql_hints": self.build_sql_hints_context(),
            "examples": self.build_examples_context()
        }
