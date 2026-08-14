from typing import Dict, Any, List, Optional
from backend.answer.models import FormattedResult


class ResultFormatter:
    def format_result(self, result: Dict[str, Any], report_name: str = "") -> FormattedResult:
        if not result or not result.get("rows"):
            return FormattedResult(
                display_type="empty",
                summary="نتیجه‌ای یافت نشد",
                details=[],
                total=0
            )
        
        rows = result.get("rows", [])
        columns = result.get("columns", [])
        row_count = result.get("row_count", 0)
        
        if row_count == 1 and len(columns) <= 3:
            return self._format_single_value(rows[0], columns, report_name)
        
        if row_count > 1:
            return self._format_table(rows, columns, report_name)
        
        return FormattedResult(
            display_type="single",
            summary=f"نتیجه: {rows[0] if rows else ''}",
            details=rows,
            total=row_count
        )
    
    def _format_single_value(self, row: Dict, columns: List[str], report_name: str) -> FormattedResult:
        if len(columns) == 1:
            value = row.get(columns[0], "")
            summary = f"نتیجه: {self._format_value(value)}"
        else:
            parts = [f"{col}: {self._format_value(row.get(col, ''))}" for col in columns]
            summary = " | ".join(parts)
        
        return FormattedResult(
            display_type="single",
            summary=summary,
            details=[row],
            total=1
        )
    
    def _format_table(self, rows: List[Dict], columns: List[str], report_name: str) -> FormattedResult:
        summary = f"تعداد نتایج: {len(rows)}"
        
        formatted_rows = []
        for row in rows[:10]:
            formatted_row = {}
            for col in columns:
                formatted_row[col] = self._format_value(row.get(col, ""))
            formatted_rows.append(formatted_row)
        
        return FormattedResult(
            display_type="table",
            summary=summary,
            details=formatted_rows,
            total=len(rows)
        )
    
    def _format_value(self, value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)


result_formatter = ResultFormatter()
