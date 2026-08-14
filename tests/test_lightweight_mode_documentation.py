from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_documents_llm_enabled_switch():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "LLM_ENABLED=true" in env_example
    assert "lightweight mode" in env_example
    assert "does not call Ollama" in env_example


def test_readme_documents_lightweight_mode():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Lightweight Mode without Ollama" in readme
    assert "LLM_ENABLED=false" in readme
    assert "mode: lightweight" in readme
    assert "/llm/chat" in readme


def test_runbook_documents_operator_steps_for_lightweight_mode():
    runbook = (ROOT / "PRODUCTION_RUNBOOK.md").read_text(encoding="utf-8")

    assert "اجرای بدون Ollama" in runbook
    assert "LLM_ENABLED=false" in runbook
    assert "llm_required: false" in runbook
    assert "API را restart کنید" in runbook
