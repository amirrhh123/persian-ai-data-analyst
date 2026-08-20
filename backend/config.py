from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Persian AI Data Analyst"
    app_version: str = "0.1.0"
    debug: bool = True
    
    database_url: str = "postgresql://postgres:postgres@localhost:5433/persian_ai_db"
    database_host: str = "localhost"
    database_port: int = 5433
    database_name: str = "persian_ai_db"
    database_user: str = "postgres"
    database_password: str = "postgres"
    
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    
    ollama_host: str = "http://localhost"
    ollama_port: int = 11434
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout: int = 60
    ollama_temperature: float = 0.1
    ollama_top_p: float = 0.9
    llm_enabled: bool = True
    llm_context_max_tokens: int = 8192
    llm_reserved_output_tokens: int = 1024
    llm_tokenizer_model_path: str = ""
    llm_provider: str = "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_url: str = "https://api.openai.com/v1/chat/completions"
    
    tenant_id: str = "education_ministry"
    
    embedding_model_path: str = "D:/projects/LLM Database/models/paraphrase-multilingual-mpnet-base-v2"
    embedding_device: str = "cpu"
    
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    
    @property
    def ollama_url(self) -> str:
        return f"{self.ollama_host}:{self.ollama_port}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
