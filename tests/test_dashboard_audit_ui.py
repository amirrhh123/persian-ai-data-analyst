from pathlib import Path


def test_dashboard_includes_sql_audit_summary_panel():
    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "پایش اجرای SQL" in html
    assert "/sql/audit/summary" in html
    assert "auditSuccess" in html
    assert "auditEvents" in html


def test_dashboard_includes_source_citation_view():
    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "renderCitations" in html
    assert "citations" in html
    assert "منابع پاسخ" in html
