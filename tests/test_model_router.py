from backend.config import Settings
from backend.llm.router import ModelRouter, RoutingRequest


def test_sensitive_requests_stay_local():
    router = ModelRouter(Settings(openai_api_key="test-key"))
    assert router.select(RoutingRequest(contains_sensitive_data=True)).__class__.__name__ == "OllamaProvider"


def test_complex_requests_use_openai_when_configured():
    router = ModelRouter(Settings(openai_api_key="test-key"))
    assert router.select(RoutingRequest(task="complex_reasoning", cost_sensitive=False)).__class__.__name__ == "OpenAIProvider"


def test_openai_falls_back_when_not_configured():
    router = ModelRouter(Settings(openai_api_key=""))
    assert router.select(RoutingRequest(task="complex_reasoning", cost_sensitive=False)).__class__.__name__ == "OllamaProvider"
