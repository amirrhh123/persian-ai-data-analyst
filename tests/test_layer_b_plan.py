from pathlib import Path


def test_layer_b_product_readiness_plan_exists():
    plan = Path("LAYER_B_PRODUCT_READINESS_PLAN.md")

    assert plan.exists()
    text = plan.read_text(encoding="utf-8")
    assert "Layer B" in text
    assert "B2 — Onboarding checklist" in text
    assert "B12 — Production runbook" in text
    assert "تعریف پایان Layer B" in text
