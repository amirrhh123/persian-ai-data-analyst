# Persian AI Data Analyst

An offline AI-powered data analyst system designed for Persian language processing and data analysis.

## Project Purpose

This project aims to build a comprehensive, offline-capable AI data analyst that can:
- Process and analyze Persian language data
- Generate SQL queries from natural language (Persian)
- Perform RAG (Retrieval-Augmented Generation) for contextual analysis
- Generate reports and visualizations

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
├─────────────────────────────────────────────────────────┤
│  API Layer      │  Agents  │  RAG  │  Validation  │ ... │
├─────────────────────────────────────────────────────────┤
│                    Services Layer                        │
├─────────────────────────────────────────────────────────┤
│  PostgreSQL (Structured Data)  │  ChromaDB (Vectors)    │
├─────────────────────────────────────────────────────────┤
│                    Ollama (Local LLM)                    │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
├── backend/
│   ├── api/              # FastAPI routes and endpoints
│   ├── agents/           # AI agent implementations (future)
│   ├── rag/              # RAG pipeline (future)
│   ├── database/         # Database models and connections
│   ├── knowledge/        # Knowledge base management
│   │   ├── models.py     # Pydantic knowledge models
│   │   ├── loader.py     # YAML file loader
│   │   ├── parser.py     # Knowledge parser
│   │   └── context_builder.py # LLM context builder
│   ├── reports/          # Report generation (future)
│   ├── validation/       # Data validation
│   ├── models/           # Data models
│   ├── services/         # Business logic
│   │   └── llm_service.py # Ollama LLM integration
│   ├── prompts/          # Persian prompt templates
│   │   ├── system_fa.txt
│   │   └── sql_generation_fa.txt
│   ├── config.py         # Configuration management
│   └── tests/            # Backend tests
├── knowledge/
│   └── tenants/          # Tenant-based knowledge files
│       └── retail_company/
│           ├── business/
│           │   ├── company.yaml
│           │   ├── definitions.yaml
│           │   ├── metrics.yaml
│           │   ├── business_rules.yaml
│           │   └── terminology.yaml
│           └── reports/
│               ├── sales_report.yaml
│               └── customer_report.yaml
├── tests/                # Integration tests
├── docker-compose.yml    # Docker services
├── .env.example          # Environment variables template
└── requirements.txt      # Python dependencies
```

## Tech Stack

- **Backend**: FastAPI + Python 3.12
- **Database**: PostgreSQL 16
- **Vector DB**: ChromaDB
- **Local AI**: Ollama (qwen2.5:7b), optional
- **Containerization**: Docker & Docker Compose

## Lightweight Mode without Ollama

The system can run without Ollama when you want a lighter product demo or a server with lower resource usage.

Set this in `.env`:

```env
LLM_ENABLED=false
```

Then restart the API server. The `/health` endpoint should show:

```text
mode: lightweight
llm_enabled: false
llm_required: false
```

In this mode, supported database questions still work through the semantic layer, templates, routing rules, and PostgreSQL execution. Direct LLM endpoints such as `/llm/chat` and `/llm/sql-test` return `503` by design because the local language model is disabled.

## Setup Instructions

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- pip or poetry

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd persian-ai-data-analyst

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings (defaults work for local development)
```

### 3. Start Services

```bash
# Start PostgreSQL and ChromaDB
docker-compose up -d

# Verify services are running
docker-compose ps
```

### 4. Install Ollama (Local AI)

This step is optional if `LLM_ENABLED=false`.

```bash
# Download and install Ollama from https://ollama.ai
# Or use winget:
winget install Ollama.Ollama

# Start Ollama service
ollama serve

# Pull the Persian-capable model (in another terminal)
ollama pull qwen2.5:7b
```

### 5. Run Application

```bash
# Start the API server
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080
```

### 6. Verify Installation

```bash
# Health check (shows Ollama status)
curl http://localhost:8080/health

# API docs
open http://localhost:8080/docs

# Test LLM chat (requires Ollama running)
curl -X POST http://localhost:8080/llm/chat -H "Content-Type: application/json" -d '{"message": "سلام"}'

# Test SQL generation (requires Ollama running)
curl -X POST http://localhost:8080/llm/sql-test -H "Content-Type: application/json" -d '{"question": "فروش ماه گذشته چقدر بوده؟"}'
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (includes Ollama status) |
| GET | `/` | API information |
| GET | `/knowledge/context` | Get business knowledge context |
| GET | `/knowledge/reports` | List all available reports |
| GET | `/knowledge/reports/{id}/context` | Get specific report context |
| POST | `/reports/groups/sync` | Sync report groups to vector store |
| POST | `/reports/groups/search` | Search for relevant group |
| POST | `/reports/sync` | Sync reports to vector store |
| POST | `/reports/search` | Two-stage search (group → report) |
| POST | `/database/sync` | Sync database schema |
| GET | `/database/schema` | Get discovered schema |
| GET | `/database/relationships` | Get table relationships |
| POST | `/sql/generate` | Generate SQL from question |
| GET | `/docs` | Swagger UI documentation |
| POST | `/llm/chat` | Chat with Persian AI assistant |
| POST | `/llm/sql-test` | Generate SQL from Persian question |

Persian user and demo question guidance: [PROMPTING_GUIDE_FA.md](PROMPTING_GUIDE_FA.md)

## Business Knowledge

The system uses a tenant-based, report-driven knowledge architecture. Each business has its own set of knowledge files organized into business rules and report definitions.

### Knowledge Pipeline

```
User Question
    ↓
Report Retrieval
    ↓
Report to Database Table Mapping
    ↓
Schema Understanding
    ↓
SQL Generation
    ↓
Execution
```

### Knowledge Files

**Business Knowledge** (`knowledge/tenants/{tenant}/business/`)

| File | Description |
|------|-------------|
| `company.yaml` | Company information (name, industry, locations) |
| `definitions.yaml` | Business term definitions |
| `metrics.yaml` | Key performance indicators (KPIs) |
| `business_rules.yaml` | Business rules and conditions |
| `terminology.yaml` | Domain-specific terminology |

**Report Definitions** (`knowledge/tenants/{tenant}/reports/`)

| File | Description |
|------|-------------|
| `sales_report.yaml` | Sales report with linked table and metrics |
| `customer_report.yaml` | Customer analysis report |

### Report Structure

Each report YAML contains:

```yaml
id: sales_report
name: گزارش فروش
description: گزارش جامع فروش محصولات
linked_table: sales
allowed_metrics:
  - فروش_روزانه
  - نرخ_تبدیل
business_rules:
  - قانون_تخفیف
example_questions:
  - فروش ماه گذشته چقدر بوده؟
```

### Adding a New Business

1. Create a new tenant directory:
```bash
mkdir -p knowledge/tenants/your_company/business
mkdir -p knowledge/tenants/your_company/reports
```

2. Add business YAML files to `business/` folder

3. Add report YAML files to `reports/` folder

4. Update `TENANT_ID` in `.env`:
```
TENANT_ID=your_company
```

5. Sync reports to vector store:
```bash
curl -X POST http://localhost:8080/reports/sync
```

6. Restart the API server

### Report Intelligence

The system uses vector embeddings for semantic report retrieval.

**Pipeline:**
```
User Question → Embedding → Vector Search → Report Match → Context Building
```

**Sync Reports:**
```bash
curl -X POST http://localhost:8080/reports/sync
```

**Search Reports:**
```bash
curl -X POST http://localhost:8080/reports/search \
  -H "Content-Type: application/json" \
  -d '{"question": "فروش ماه گذشته چقدر بوده؟"}'
```

**Configuration:**
```env
EMBEDDING_MODEL_PATH=D:/projects/LLM Database/models/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DEVICE=cpu
```

**Note:** The embedding model must be downloaded locally in `models/` directory. The system is fully offline.

## Database Discovery

The system automatically discovers database schema from PostgreSQL using `information_schema`.

**Pipeline:**
```
PostgreSQL → information_schema → Tables/Columns → Foreign Keys → Relationship Graph
```

**Sync Schema:**
```bash
curl -X POST http://localhost:8080/database/sync
```

**Get Schema:**
```bash
curl http://localhost:8080/database/schema
```

**Get Relationships:**
```bash
curl http://localhost:8080/database/relationships
```

### Education Sample Database

The sample database includes:

| Table | Description |
|-------|-------------|
| `organization_units` | ساختار سازمانی |
| `employees` | کارکنان |
| `salary_items` | اقلام حقوقی |
| `ranking_requests` | درخواست‌های ارتقا |
| `retirement_records` | سوابق بازنشستگی |
| `schools` | مدارس |
| `students` | دانش‌آموزان |

### Automatic Relationships

```
salary_items.employee_id → employees.id
employees.organization_unit_id → organization_units.id
ranking_requests.employee_id → employees.id
retirement_records.employee_id → employees.id
schools.organization_unit_id → organization_units.id
students.school_id → schools.id
```

## Two-Stage Report Intelligence

The system uses a two-stage retrieval approach:

**Pipeline:**
```
Question → Group Retrieval → Report Retrieval → Table Mapping
```

**Stage 1: Find Group**
```bash
curl -X POST http://localhost:8080/reports/groups/search \
  -H "Content-Type: application/json" \
  -d '{"question": "حقوق ماه گذشته چقدر بوده؟"}'
```

**Stage 2: Find Report in Group**
```bash
curl -X POST http://localhost:8080/reports/search \
  -H "Content-Type: application/json" \
  -d '{"question": "حقوق ماه گذشته چقدر بوده؟"}'
```

**Education Groups:**

| Group | Description |
|-------|-------------|
| `salary` | گروه حقوق و مزایا |
| `employee` | گروه کارکنان |
| `organization` | گروه ساختار سازمانی |
| `ranking` | گروه ارتقای رتبه |
| `student` | گروه دانش‌آموزان |

## SQL Planning + Generation + Validation

The system generates SQL through a structured pipeline:

**Pipeline:**
```
Question → SQL Planner → SQL Generator → SQL Validator → Safe SQL
```

**Generate SQL:**
```bash
curl -X POST http://localhost:8080/sql/generate \
  -H "Content-Type: application/json" \
  -d '{"question": "لیست دانش آموزان"}'
```

### SQL Planner
- Detects tables from Persian keywords
- Identifies joins from schema relationships
- Detects aggregations (COUNT, SUM, AVG)
- Adds filters based on context

### SQL Generator
- Uses local Ollama Qwen model
- Takes plan + schema context
- Generates SELECT-only queries

### SQL Validator
- **SELECT only** - Rejects DROP, DELETE, UPDATE, INSERT
- **Table whitelist** - Only discovered schema tables
- **Column validation** - Warns about unknown columns
- **Syntax check** - Validates parentheses

## Structured Knowledge Architecture

The knowledge layer provides structured context for maximum SQL accuracy:

**Knowledge Structure:**
```
knowledge/tenants/{tenant}/
├── business/
│   ├── company.yaml
│   ├── definitions.yaml
│   ├── metrics.yaml
│   └── terminology.yaml
├── groups/
│   ├── salary.yaml
│   ├── employee.yaml
│   └── ...
├── reports/
│   ├── salary_summary.yaml
│   ├── employee_list.yaml
│   └── ...
└── rules/
    └── business_rules.yaml
```

### Report Metadata

Each report includes:

| Field | Description |
|-------|-------------|
| `important_columns` | Column meanings for SQL generation |
| `sql_hints.default_filters` | Automatic WHERE clauses |
| `sql_hints.preferred_joins` | Recommended JOIN paths |
| `sql_hints.group_by_columns` | GROUP BY suggestions |

**Example:**
```yaml
important_columns:
  net_salary:
    meaning: خالص پرداختی
    persian_name: خالص حقوق
sql_hints:
  default_filters:
    - "status = 'active'"
  preferred_joins:
    - "salary_items.employee_id = employees.id"
```

### SQL Generation Context

The prompt builder combines:
- Business Context (company info, definitions)
- Group Context (report group)
- Report Context (columns, hints, rules)
- Schema Context (tables, columns, relationships)

This ensures the LLM generates accurate SQL without guessing business logic.

### API Endpoints for Knowledge

```bash
# Get business context
curl http://localhost:8080/knowledge/context

# List all reports
curl http://localhost:8080/knowledge/reports

# Get specific report context
curl http://localhost:8080/knowledge/reports/sales_report/context
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_api.py
```

### Code Quality

```bash
# Install dev dependencies
pip install black flake8 mypy

# Format code
black backend/ tests/

# Lint code
flake8 backend/ tests/

# Type checking
mypy backend/
```

## Troubleshooting

### Ollama

**Ollama not running / connection refused**
```bash
# Check if Ollama is running
ollama list
# Start Ollama service
ollama serve
# Verify Ollama is accessible
curl http://localhost:11434/api/tags
```

**Model not found**
```bash
# List available models
ollama list
# Pull the required model
ollama pull qwen2.5:7b
```

**LLM timeout errors**
```bash
# Increase timeout in .env
OLLAMA_TIMEOUT=120
# Or use a smaller model
ollama pull qwen2.5:3b
```

### Docker Services

**PostgreSQL won't start (port 5433 already in use)**
```bash
# Find process using the port
netstat -ano | findstr :5433
# Kill it or change DATABASE_PORT in .env
```

**ChromaDB healthcheck fails**
```bash
# Check container logs
docker logs persian_ai_chromadb
# Restart the service
docker-compose restart chromadb
```

**Services not healthy after start**
```bash
# Check health status
docker-compose ps
# View logs for unhealthy container
docker logs persian_ai_postgres
# Force recreate
docker-compose down -v && docker-compose up -d
```

### Python / API

**ModuleNotFoundError: No module named 'pytest'**
```bash
# Ensure you're using Python 3.12, not hermes venv
"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
"C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_api.py -v
```

**Config changes not taking effect**
```bash
# Settings are cached via @lru_cache — restart the API server
# Kill uvicorn and restart
```

**Connection refused to PostgreSQL**
```bash
# Verify container is running and healthy
docker-compose ps
# Test connection directly
docker exec persian_ai_postgres pg_isready -U postgres
```

### General

**Docker Compose command not found**
```bash
# Use docker compose (v2) instead of docker-compose
docker compose up -d
```

**Permission denied on volumes**
```bash
# Reset Docker volumes
docker-compose down -v
docker-compose up -d
```

## Future Phases

### Phase 1: Core AI Integration
- [x] Ollama integration for local LLM
- [x] Persian language processing pipeline
- [x] Basic SQL generation

### Phase 2: Business Knowledge Layer
- [x] Tenant-based knowledge architecture
- [x] YAML knowledge file system
- [x] Context builder for LLM
- [x] Multi-business support
- [x] Report-driven architecture
- [x] Report context builder

### Phase 3: Report Intelligence
- [x] ChromaDB integration
- [x] Embedding service (configurable)
- [x] Report sync endpoint
- [x] Report search endpoint
- [x] Multi-tenant vector isolation

### Phase 4: Database Schema Discovery
- [x] PostgreSQL schema discovery
- [x] Automatic table/column extraction
- [x] Foreign key detection
- [x] Relationship graph
- [x] Schema metadata storage

### Phase 4.5: Two-Stage Report Intelligence
- [x] Report groups concept
- [x] Group retrieval with ChromaDB
- [x] Two-stage search (group → report)
- [x] Education tenant with 5 groups

### Phase 5: SQL Planning + Generation + Validation
- [x] SQL Planner (table detection, joins, aggregations)
- [x] SQL Generator (Ollama integration)
- [x] SQL Validator (SELECT only, forbidden keywords, table whitelist)
- [x] Prompt Builder for LLM context
- [x] SQL API endpoint

### Phase 5.6: Benchmark System
- [x] Benchmark dataset with 20 test cases
- [x] Evaluator for group/report/table accuracy
- [x] Performance metrics (retrieval, planning, total time)
- [x] Report generation with category breakdown
- [x] CLI command for running benchmarks

### Phase 5.9.2: Entity Priority Scoring
- [x] EntityTerm model with weighted terms
- [x] Entity-based scoring in group retriever
- [x] 95% group accuracy achieved

### Phase 6: Safe SQL Execution
- [x] SQL Execution Service
- [x] SQL Limiter (SELECT only, forbidden keywords)
- [x] Row limit and timeout support
- [x] Execution time measurement
- [x] Execution API endpoint

### Phase 6.5: Full Query Pipeline
- [x] Pipeline orchestration (Group → Report → SQL → Execute)
- [x] Trace logging with timing
- [x] Pipeline API endpoint
- [x] Integration tests

### Phase 7: Persian Answer Generation
- [x] Answer Generator with local LLM
- [x] Result Formatter (single/table/empty)
- [x] Prompt Builder for Persian responses
- [x] Pipeline integration with answer step

### Phase 8: Multi-Tenant & Deployment
- [ ] ChromaDB vector storage
- [ ] Document ingestion pipeline
- [ ] Context-aware query processing

### Phase 3: Agent System
- [ ] Multi-agent orchestration
- [ ] Specialized analysis agents
- [ ] Tool integration

### Phase 4: Advanced Features
- [ ] Report generation
- [ ] Data visualization
- [ ] Batch processing
- [ ] API authentication

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | Persian AI Data Analyst | Application name |
| `APP_VERSION` | 0.1.0 | Application version |
| `DEBUG` | true | Debug mode |
| `DATABASE_URL` | postgresql://... | PostgreSQL connection string |
| `DATABASE_PORT` | 5433 | PostgreSQL port |
| `CHROMA_HOST` | localhost | ChromaDB host |
| `CHROMA_PORT` | 8000 | ChromaDB port |
| `OLLAMA_HOST` | http://localhost | Ollama host |
| `OLLAMA_PORT` | 11434 | Ollama port |
| `OLLAMA_MODEL` | qwen2.5:7b | Ollama model name |
| `OLLAMA_TIMEOUT` | 60 | LLM request timeout (seconds) |
| `OLLAMA_TEMPERATURE` | 0.1 | Generation temperature (lower = more deterministic) |
| `OLLAMA_TOP_P` | 0.9 | Top-p sampling (0.9 recommended for data analysis) |
| `TENANT_ID` | retail_company | Active business tenant ID |
| `API_HOST` | 0.0.0.0 | API server host |
| `API_PORT` | 8080 | API server port |

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]
