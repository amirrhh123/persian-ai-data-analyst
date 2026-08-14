# Persian AI Data Analyst

An offline-first Persian natural-language interface for relational databases. The system discovers a PostgreSQL schema, builds a semantic layer, retrieves relevant business context, generates safe SQL, validates it, and presents the result in Persian.

## Why this project

Business users often know the question they want to ask but do not know SQL or the database structure. This project turns questions such as:

```text
تعداد دانش‌آموزان استان تهران چقدر است؟
اطلاعات کارمندان فعال واحدهای تهران را نشان بده
تعداد درخواست‌ها با پست کارمند اداری
```

into validated, read-only SQL and a structured Persian answer.

## Highlights

- Persian intent detection and normalization
- Automatic PostgreSQL schema discovery
- Versioned semantic catalog with human review
- Hybrid retrieval: dense embeddings plus lexical BM25-style ranking
- Explainable second-stage reranking with phrase, token, and metadata evidence
- Confidence gating for weak, unsupported, or ambiguous retrieval results
- Generic Value Index for discovering filters from database values
- Deterministic SQL planning with optional Ollama fallback
- Join-path, aggregate, identifier, and result-shape validation
- Read-only execution limits, sensitive-data policies, and audit logs
- Automatic semantic lifecycle for newly added tables
- Regression benchmarks and generated smoke tests
- RTL dashboard and non-technical administration workflow
- Lightweight mode that can run without Ollama

## Architecture

```mermaid
flowchart LR
    U["Persian question"] --> I["Intent and ambiguity detection"]
    I --> R["Hybrid retrieval"]
    R --> RR["Explainable reranker"]
    RR --> G["Confidence gate"]
    G --> S["Semantic catalog and Value Index"]
    S --> P["Deterministic SQL planner"]
    P --> V["Safety and SQL validation"]
    V --> DB[(PostgreSQL)]
    DB --> A["Persian answer formatter"]
    C[(ChromaDB)] --> R
    O["Ollama - optional"] --> P
```

ChromaDB stores embeddings and retrieval metadata. PostgreSQL remains the source of truth for organizational data. Model weights are not fine-tuned or stored in this repository.

## Technology stack

| Area | Technology |
|---|---|
| API | Python 3.12, FastAPI, Pydantic |
| Database | PostgreSQL 16, SQLAlchemy |
| Retrieval | ChromaDB, sentence-transformers, hybrid lexical scoring, second-stage reranking |
| Local LLM | Ollama with `qwen2.5:7b` (optional) |
| UI | RTL HTML/CSS/JavaScript, Vazirmatn |
| Testing | pytest, semantic smoke tests, regression benchmarks |
| Runtime | Docker Compose |

## Quick start

### Requirements

- Python 3.12+
- Docker Desktop with Docker Compose
- Ollama only when `LLM_ENABLED=true`
- A locally downloaded multilingual sentence-transformer model

### Installation

```powershell
git clone <repository-url>
cd persian-ai-data-analyst

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

Copy-Item .env.example .env
docker compose up -d
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080
```

Open:

- Dashboard: <http://localhost:8080/dashboard>
- API documentation: <http://localhost:8080/docs>
- Health check: <http://localhost:8080/health>

For the complete setup and database initialization workflow, see [SETUP_TUTORIAL.md](SETUP_TUTORIAL.md).

## Configuration

Copy `.env.example` to `.env`. Important settings:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/persian_ai_db
CHROMA_HOST=localhost
CHROMA_PORT=8001
TENANT_ID=education_ministry
EMBEDDING_MODEL_PATH=./models/paraphrase-multilingual-mpnet-base-v2
LLM_ENABLED=true
OLLAMA_MODEL=qwen2.5:7b
```

Model files, database dumps, generated tenant artifacts, logs, and benchmark outputs are intentionally excluded from Git.

## Lightweight mode

The deterministic semantic and SQL layers can operate without Ollama:

```env
LLM_ENABLED=false
```

Restart the API after changing environment variables. In lightweight mode, supported database questions continue to work, while direct LLM endpoints return `503` by design.

## Semantic onboarding workflow

When a new database or table is introduced, the lifecycle performs:

1. Schema and relationship discovery
2. Validator schema synchronization
3. Schema quality checks
4. Semantic table and column suggestions
5. Generic Value Index generation
6. Human-reviewed semantic activation
7. Smoke tests and regression benchmark

This keeps database content in PostgreSQL while regenerating only the metadata required for understanding and safe SQL generation.

## Safety model

- Only read-only SQL is allowed
- Table, column, join, and aggregate references are validated
- Row count and execution-time limits are enforced
- Sensitive columns are governed by data policies
- Primary keys, unique identifiers, national IDs, phone numbers, and secrets are excluded from the Value Index
- Ambiguous or unsupported questions fail closed
- Query decisions and execution outcomes are auditable

## Testing

Run focused unit and regression tests:

```powershell
python -m pytest tests/test_confidence_gate.py tests/test_reranker.py tests/test_hybrid_retrieval.py tests/test_value_index.py -v
python -m pytest tests/test_regression_benchmark.py -v
```

Run the complete suite when PostgreSQL and ChromaDB are available:

```powershell
python -m pytest tests -v
```

Some integration tests require the local embedding model and Docker services.

## Repository structure

```text
backend/
  api/             FastAPI endpoints and dashboard
  database/        discovery, onboarding, and schema graph
  pipeline/        intent routing and end-to-end query flow
  reports/         embeddings, ChromaDB, and hybrid retrieval
  semantic/        semantic lifecycle and human review
  sql/             planning, building, and validation
  value_index/     generic categorical value retrieval
knowledge/         sample business metadata
database_scripts/  sample PostgreSQL schema and generators
tests/             unit, integration, smoke, and regression tests
```

## Documentation

- [Demo questions](DEMO_QUESTIONS.md)
- [Setup tutorial](SETUP_TUTORIAL.md)
- [System operation guide](SYSTEM_OPERATION_GUIDE.md)
- [Production runbook](PRODUCTION_RUNBOOK.md)

## Current limitations

- PostgreSQL is the production database adapter currently implemented
- Embedding weights must be downloaded separately
- Fully generic onboarding still benefits from human review of business terminology
- The included database and questions are synthetic portfolio data

## License

Released under the [MIT License](LICENSE).
