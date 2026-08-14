from pathlib import Path


def test_dashboard_includes_sql_audit_summary_panel():
    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "پایش اجرای SQL" in html
    assert "/sql/audit/summary" in html
    assert "auditSuccess" in html
    assert "auditEvents" in html
