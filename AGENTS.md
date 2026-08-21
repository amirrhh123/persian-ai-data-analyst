# AGENTS.md

## Project

Persian AI Data Analyst — offline AI system for Persian language data analysis, SQL generation, and RAG. Currently Phase 1 (local AI engine).

## Quick Commands

```powershell
# CRITICAL: Shell defaults to hermes venv (Python 3.11) — pytest/uvicorn won't work there
# Always use Python 3.12 explicitly with & operator:

# Install deps
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt

# Run tests
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_api.py -v

# Start API server (port 8080)
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080

# Docker services (PostgreSQL on 5433, ChromaDB on 8000)
docker-compose up -d
```

## Architecture

- **Entry point**: `backend/api/main.py` — FastAPI app
- **Config**: `backend/config.py` — Pydantic Settings, loads `.env`
- **LLM**: `backend/services/llm_service.py` — Ollama integration
- **Prompts**: `backend/prompts/` — Persian prompt templates
- **Docker**: PostgreSQL 16 (port 5433) + ChromaDB (port 8000)
- **Ollama**: qwen2.5:7b model (port 11434)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (includes Ollama status) |
| GET | `/` | API information |
| POST | `/llm/chat` | Chat with Persian AI |
| POST | `/llm/sql-test` | Generate SQL from Persian question |

## Gotchas

- PostgreSQL maps to host port **5433** (not 5432) to avoid conflicts
- ChromaDB not installed locally (requires MSVC build tools) — runs in Docker only
- Shell defaults to hermes-agent venv Python 3.11 — use Python 3.12 explicitly
- PowerShell requires `&` before quoted executable paths
- `backend/config.py` uses `@lru_cache()` on `get_settings()` — env changes require restart
- Tests use `fastapi.testclient.TestClient` (sync), not async test client
- Tests mock Ollama — no internet required to run them

## Project Status

Phase 1 complete. LLM integration with Ollama working. `/llm/chat` and `/llm/sql-test` endpoints active.
