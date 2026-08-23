# AGENTS.md

Persian AI Data Analyst — offline Persian natural-language → SQL system over PostgreSQL (FastAPI, ~100 modules under `backend/`). Multi-tenant; active tenant set in `.env`.

## Commands

Shell defaults to a Python 3.11 venv without project deps. **Always invoke Python 3.12 explicitly** (PowerShell needs `&` before quoted paths):

```powershell
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_sql_templates.py -q   # single test file
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pytest "tests/test_api.py::test_health_endpoint" -q  # single test
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn backend.api.main:app --reload --port 8090
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
docker compose up -d   # postgres 5433->5432, chromadb 8001->8000, api (Dockerfile build)
```

- Run pytest from repo root — there is no pytest.ini/conftest/pyproject; tests import `backend.*` relative to root.
- No lint/format/typecheck tooling is configured despite README mentions.

## Testing quirks

- Most unit tests are fast (<1 s/file) and fully offline (Ollama mocked). Good smoke files: `tests/test_intent_detection.py`, `tests/test_sql_templates.py`, `tests/test_semantic_versioning.py`.
- Some semantic/schema tests connect to **live PostgreSQL on localhost:5433** and fail if `docker compose up -d postgres` hasn't been run (e.g. `tests/test_semantic_catalog.py`).
- `tests/test_api.py` is stale: it loads tenant YAML from `knowledge/tenants/` (that directory is now empty) and requires ChromaDB plus the local embedding model (slow model load). Don't treat its failures as your regression; prefer targeted newer test files.
- Benchmark/regression runners persist result JSON into `tests/results/`.

## Config gotchas

- Current `.env`: `API_PORT=8090`, `OLLAMA_MODEL=gemma3:12b`, `TENANT_ID=education_ministry`.
- DB connections use `DATABASE_URL` (defaults to `...@localhost:5433/persian_ai_db`). The separate `DATABASE_NAME/HOST/PORT` settings are not what `backend/database/connection.py` consumes — edit `DATABASE_URL` to change targets.
- `get_settings()` is `@lru_cache`-wrapped: `.env` changes require restarting the process.
- LLM is optional: `LLM_ENABLED=false` = lightweight mode (deterministic templates + semantic layer only); `/llm/chat` and `/llm/sql-test` then return 503 by design.
- Embedding model must exist locally at `models/paraphrase-multilingual-mpnet-base-v2`; nothing downloads at runtime.

## Architecture

- Entry point: `backend/api/main.py` (all routes inline, ~790 lines). Core orchestrator: `backend/pipeline/query_pipeline.py` (~2.4k lines).
- Query flow: Persian question → intent extraction → semantic resolution (`semantic/resolver.py`) → safety gates (`pipeline/safety/`) that emit Persian clarification questions instead of guessing → deterministic SQL plan (`sql/templates.py`, ~1.4k lines) → validation (`sql/validator.py`) → Postgres execution → Persian answer generation.
- Known entities (student, employee, school, salary, retirement, ranking, organization) route to hand-built deterministic planners; generic semantic routing is reserved for newly discovered tables — don't reroute known entities through the generic path.
- Tenant state lives in `schema/tenants/{tenant}/`: `tables.json`, `relationships.json`, `discovery.json`, `value_index.json`, and `semantic_active.json` (the activated semantic catalog). `knowledge/` is legacy/empty.
- Semantic layer lifecycle (scripts in `scripts/`): discover → suggestions → review → activate (blocked unless ≥95% benchmark pass rate) → versioned snapshots with rollback; freshness/auto-update/incremental sync built on top.
- SQL safety is layered: SELECT-only validator, table whitelist, aggregate guard, join verifier, execution limiter/audit (`execution/`).

## Conventions

- All user-facing strings (questions, clarifications, answers, errors) are Persian; code identifiers are English. Preserve this split.
- Docs of note: `ThingsMustDo.md` (production roadmap, Persian), `PRODUCTION_RUNBOOK.md`, `PROMPTING_GUIDE_FA.md` (demo-question phrasing rules that affect retrieval accuracy).
- `output/pdf/` contains stray Edge browser-profile artifacts from PDF generation — don't commit changes there.
