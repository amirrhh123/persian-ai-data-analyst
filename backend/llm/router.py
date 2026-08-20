from dataclasses import dataclass
from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


@dataclass(frozen=True)
class RoutingRequest:
    """Signals used by the routing policy; callers may pass only what they know."""
    contains_sensitive_data: bool = False
    task: str = "general"
    complexity: str = "normal"
    cost_sensitive: bool = True
    latency_sensitive: bool = False
    provider_healthy: dict[str, bool] | None = None


class ModelRouter:
    def __init__(self, settings):
        self.settings = settings
        self.providers = {"ollama": OllamaProvider(settings)}
        if settings.openai_api_key:
            self.providers["openai"] = OpenAIProvider(settings)

    def select(self, request: RoutingRequest | str | None = None) -> LLMProvider:
        if isinstance(request, str):
            name = request
        elif request is None:
            name = self.settings.llm_provider
        else:
            # Sensitive data and low latency/cost requirements stay local.
            if request.contains_sensitive_data or request.cost_sensitive or request.latency_sensitive:
                name = "ollama"
            elif request.task in {"complex_reasoning", "long_context"} or request.complexity == "high":
                name = "openai"
            else:
                name = self.settings.llm_provider
            if request.provider_healthy and not request.provider_healthy.get(name, True):
                name = "ollama"
        if name == "openai" and "openai" not in self.providers:
            name = "ollama"
        if name not in self.providers:
            raise ValueError(f"Unsupported LLM provider: {name}")
        return self.providers[name]
