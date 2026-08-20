import httpx

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        payload = {"model": self.settings.openai_model, "messages": messages,
                   "temperature": self.settings.ollama_temperature}
        async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
            response = await client.post(self.settings.openai_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

