import httpx
from time import perf_counter
from uuid import uuid4
from typing import Optional
from backend.config import get_settings
from backend.llm.context_budget import ContextBudget
from backend.llm.models import TokenUsage
from backend.llm.token_counter import create_token_counter
from backend.llm.router import ModelRouter
from backend.observability.llm_events import LLMEvent, event_store
from backend.observability.cost_calculator import ModelPricing, estimate_cost


class LLMService:
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.ollama_url
        self.token_counter = create_token_counter(self.settings.llm_tokenizer_model_path)
        self.context_budget = ContextBudget(self.settings.llm_context_max_tokens, self.settings.llm_reserved_output_tokens)
        self.last_usage: TokenUsage | None = None
        self.router = ModelRouter(self.settings)

    def _fit_prompts(self, prompt: str, system_prompt: Optional[str]) -> tuple[str, Optional[str]]:
        system = system_prompt or ""
        system_tokens = self.token_counter.count(system)
        remaining = max(1, self.context_budget.available_input_tokens - system_tokens)
        user_budget = ContextBudget(remaining, 0, self.context_budget.truncation_marker)
        return user_budget.fit(prompt, self.token_counter).text, system_prompt

    def _record_usage(self, data: dict, prompt: str, output: str) -> None:
        input_tokens = int(data.get("prompt_eval_count", self.token_counter.count(prompt)))
        output_tokens = int(data.get("eval_count", self.token_counter.count(output)))
        self.last_usage = TokenUsage(input_tokens, output_tokens, input_tokens + output_tokens)
    
    async def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        if not self.settings.llm_enabled:
            raise RuntimeError("LLM/Ollama is disabled. Enable LLM_ENABLED=true to use this endpoint.")

        message, system_prompt = self._fit_prompts(message, system_prompt)
        payload = {
            "model": self.settings.ollama_model,
            "messages": [],
            "stream": False,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
                "num_predict": self.settings.llm_reserved_output_tokens,
            }
        }
        
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        
        payload["messages"].append({"role": "user", "content": message})
        
        started = perf_counter()
        provider = self.router.select()
        try:
            output = await provider.chat(message, system_prompt)
        except Exception:
            event_store.record(LLMEvent(str(uuid4()), self.settings.llm_provider, self.settings.ollama_model,
                                        0, 0, (perf_counter()-started)*1000, 0.0, False))
            raise
        self.last_usage = getattr(provider, "last_usage", None)
        usage = self.last_usage or TokenUsage(self.token_counter.count(message), self.token_counter.count(output), 0)
        event_store.record(LLMEvent(str(uuid4()), self.settings.llm_provider, self.settings.ollama_model,
                                    usage.input_tokens, usage.output_tokens, (perf_counter()-started)*1000,
                                    estimate_cost(usage.input_tokens, usage.output_tokens, ModelPricing()), True))
        return output
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.settings.llm_enabled:
            raise RuntimeError("LLM/Ollama is disabled. Enable LLM_ENABLED=true to use this endpoint.")

        prompt, system_prompt = self._fit_prompts(prompt, system_prompt)
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
                "num_predict": self.settings.llm_reserved_output_tokens,
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        started = perf_counter()
        provider = self.router.select()
        try:
            output = await provider.generate(prompt, system_prompt)
        except Exception:
            event_store.record(LLMEvent(str(uuid4()), self.settings.llm_provider, self.settings.ollama_model,
                                        0, 0, (perf_counter()-started)*1000, 0.0, False))
            raise
        self.last_usage = getattr(provider, "last_usage", None)
        usage = self.last_usage or TokenUsage(self.token_counter.count(prompt), self.token_counter.count(output), 0)
        event_store.record(LLMEvent(str(uuid4()), self.settings.llm_provider, self.settings.ollama_model,
                                    usage.input_tokens, usage.output_tokens, (perf_counter()-started)*1000,
                                    estimate_cost(usage.input_tokens, usage.output_tokens, ModelPricing()), True))
        return output
    
    async def is_connected(self) -> bool:
        if not self.settings.llm_enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    async def list_models(self) -> list:
        if not self.settings.llm_enabled:
            return []
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


llm_service = LLMService()
