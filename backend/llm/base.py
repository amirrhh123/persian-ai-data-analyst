from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    async def chat(self, message: str, system_prompt: str | None = None) -> str:
        return await self.generate(message, system_prompt)

