import httpx
from typing import Optional
from backend.config import get_settings


class LLMService:
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.ollama_url
    
    async def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        if not self.settings.llm_enabled:
            raise RuntimeError("LLM/Ollama is disabled. Enable LLM_ENABLED=true to use this endpoint.")

        payload = {
            "model": self.settings.ollama_model,
            "messages": [],
            "stream": False,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p
            }
        }
        
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        
        payload["messages"].append({"role": "user", "content": message})
        
        async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.settings.llm_enabled:
            raise RuntimeError("LLM/Ollama is disabled. Enable LLM_ENABLED=true to use this endpoint.")

        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["response"]
    
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
