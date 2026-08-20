from backend.observability.cost_calculator import ModelPricing, estimate_cost
from backend.observability.llm_events import LLMEvent, LLMEventStore
from backend.observability.metrics import current_metrics
from backend.observability.redaction import redact_sensitive


def test_cost_and_redaction():
    assert estimate_cost(1000, 500, ModelPricing(2.0, 4.0)) == 4.0
    assert "1234567890" not in redact_sensitive("کد 1234567890")


def test_event_store_metrics():
    store = LLMEventStore()
    store.record(LLMEvent("q", "ollama", "qwen", 10, 2, 20, 0, True))
    assert len(store.snapshot()) == 1
