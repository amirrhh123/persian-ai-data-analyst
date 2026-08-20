from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


class ModelRouter:
    def __init__(self, settings):
        self.settings = settings
        self.providers = {"ollama": OllamaProvider(settings)}
        if settings.openai_api_key:
            self.providers["openai"] = OpenAIProvider(settings)

    def select(self, provider_name: str | None = None) -> LLMProvider:
        name = provider_name or self.settings.llm_provider
        if name not in self.providers:
            raise ValueError(f"Unsupported LLM provider: {name}")
        return self.providers[name]

