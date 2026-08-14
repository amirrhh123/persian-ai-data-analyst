from pathlib import Path


def test_dashboard_includes_layer_b_admin_controls():
    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "adminSyncDiscovery" in html
    assert "adminQualityGate" in html
    assert "adminSmokeSync" in html
    assert "adminSmokeRun" in html
    assert "adminLightweightReadiness" in html
    assert "adminLightweightGaps" in html
    assert "adminApplyLightweightGaps" in html
    assert "adminReviewApply" in html
    assert "adminDataPolicy" in html
    assert "adminErrorTaxonomy" in html
    assert "/database/discovery/sync" in html
    assert "/database/schema-quality-gate" in html
    assert "/semantic/smoke-tests/sync" in html
    assert "/semantic/smoke-tests/run" in html
    assert "/semantic/lightweight-readiness" in html
    assert "/semantic/lightweight-gap-suggestions" in html
    assert "/semantic/lightweight-gap-suggestions/apply" in html
    assert "validation_status" in html
    assert "next_action" in html
    assert "suggested_review_payload" in html
    assert "/semantic/review" in html
    assert "/security/data-policy" in html
    assert "/errors/taxonomy" in html
    assert "renderExplanation" in html
    assert "max-width:1120px" in html


def test_dashboard_admin_help_is_static_and_nontechnical():
    html = Path("backend/api/dashboard.html").read_text(encoding="utf-8")

    assert "راهنمای ساده پنل ادمین" in html
    assert "این بخش برای مسئول سیستم است" in html
    assert "نتیجه کارهایی که از پنل ادمین انجام می‌دهید" in html
    assert "اصلاح معنی توسط انسان" in html
    assert "خواندن اطلاعات دیتابیس" in html
    assert "بررسی سلامت دیتابیس" in html
    assert "ساخت سؤال تستی" in html
    assert "اجرای سؤال‌های تستی" in html
    assert "به‌روزرسانی کامل سیستم" in html
    assert "نام جدول" in html
    assert "نام ستون" in html
    assert "عبارت فارسی" in html
    assert "بعد از ثبت اصلاح" in html
