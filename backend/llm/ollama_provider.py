import httpx

from .base import LLMProvider
from .models import TokenUsage


class OllamaProvider(LLMProvider):
    def __init__(self, settings):
        self.settings = settings
        self.last_usage: TokenUsage | None = None

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        payload = {"model": self.settings.ollama_model, "prompt": prompt, "stream": False,
                   "options": {"temperature": self.settings.ollama_temperature,
                               "top_p": self.settings.ollama_top_p,
                               "num_predict": self.settings.llm_reserved_output_tokens}}
        if system_prompt:
            payload["system"] = system_prompt
        async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
            response = await client.post(f"{self.settings.ollama_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        output = data["response"]
        self.last_usage = TokenUsage(int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0)),
                                     int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0)))
        return output

    async def chat(self, message: str, system_prompt: str | None = None) -> str:
        payload = {"model": self.settings.ollama_model, "messages": [], "stream": False,
                   "options": {"temperature": self.settings.ollama_temperature,
                               "top_p": self.settings.ollama_top_p,
                               "num_predict": self.settings.llm_reserved_output_tokens}}
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": message})
        async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
            response = await client.post(f"{self.settings.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        output = data["message"]["content"]
        self.last_usage = TokenUsage(int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0)),
                                     int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0)))
        return output

