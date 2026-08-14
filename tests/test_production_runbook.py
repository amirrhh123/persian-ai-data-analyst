from pathlib import Path


def test_production_runbook_exists_and_covers_layer_b_operations():
    runbook = Path("PRODUCTION_RUNBOOK.md")

    assert runbook.exists()
    text = runbook.read_text(encoding="utf-8")
    required_sections = [
        "Onboarding دیتابیس جدید",
        "Schema quality gate",
        "Human review",
        "Smoke-test",
        "Rollback",
        "Audit",
        "امنیت داده",
        "Error taxonomy",
        "چک‌لیست قبل از ارائه به کارفرما",
    ]
    for section in required_sections:
        assert section in text


def test_layer_b_plan_marks_b12_done():
    text = Path("LAYER_B_PRODUCT_READINESS_PLAN.md").read_text(encoding="utf-8")

    assert "B12 — Production runbook" in text
    assert "وضعیت: انجام شد" in text
    assert "PRODUCTION_RUNBOOK.md" in text
