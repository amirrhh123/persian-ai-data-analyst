# Client Deployment and External PostgreSQL Setup Guide

## Purpose

This guide is intended for the client's IT team or PostgreSQL database administrator. It explains how to deploy the Persian AI Data Analyst and connect it to an organizational PostgreSQL database without sharing database credentials with the software provider.

The application must use a dedicated read-only PostgreSQL account. It must not be granted permission to create, modify, or delete organizational data.

## Target Architecture

```text
Organizational PostgreSQL Database
                ↑
        FastAPI API in Docker
                ↓
         ChromaDB in Docker
                ↓
        Ollama on Windows Host
```

## 1. System Requirements

The Windows host should have:

- Windows 10 or Windows 11, 64-bit
- At least 16 GB of RAM
- At least 25 GB of free disk space
- Hardware virtualization enabled
- Administrator access for installation
- Network access to the PostgreSQL server
- Internet access during initial installation

## 2. Install Required Software

Install the following applications:

- Docker Desktop with the WSL 2 backend
- Ollama for Windows
- Git for Windows

Restart Windows after installing Docker Desktop.

Verify the installations in PowerShell:

```powershell
docker --version
docker compose version
ollama --version
git --version
```

Docker Desktop must be open and report that Docker is running.

## 3. Install the Ollama Model

Install the selected local language model:

```powershell
ollama pull gemma3:12b
```

Verify that the model is available:

```powershell
ollama list
```

Test it directly:

```powershell
ollama run gemma3:12b
```

Enter a short Persian test prompt, then type `/bye` to exit.

Verify the Ollama API:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## 4. Obtain the Application

Clone the repository:

```powershell
git clone https://github.com/amirrhh123/persian-ai-data-analyst.git
cd persian-ai-data-analyst
```

The following large files are not stored in GitHub and must be downloaded or transferred separately:

```text
docker_wheels/torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
models/paraphrase-multilingual-mpnet-base-v2/
```

### CPU-only PyTorch wheel

Download the Linux CPython 3.12 CPU wheel from the official PyTorch index:

```text
https://download-r2.pytorch.org/whl/cpu/torch-2.12.1%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl
```

Place it at:

```text
docker_wheels/torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
```

### Embedding model

Download the model from:

```text
https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2/tree/main
```

Required structure:

```text
models/
└── paraphrase-multilingual-mpnet-base-v2/
    ├── 1_Pooling/
    │   └── config.json
    ├── config.json
    ├── config_sentence_transformers.json
    ├── model.safetensors
    ├── modules.json
    ├── sentence_bert_config.json
    ├── sentencepiece.bpe.model
    ├── special_tokens_map.json
    ├── tokenizer.json
    └── tokenizer_config.json
```

The ONNX, OpenVINO, TensorFlow, and duplicate `pytorch_model.bin` files are not required.

Verify the required files:

```powershell
Test-Path "docker_wheels\torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl"
Test-Path "models\paraphrase-multilingual-mpnet-base-v2\model.safetensors"
Test-Path "models\paraphrase-multilingual-mpnet-base-v2\1_Pooling\config.json"
```

All three commands must return `True`.

## 5. Create a Read-Only PostgreSQL Account

The database administrator must create a dedicated account. Replace the database name, schema name, and password with the organization's actual values.

```sql
CREATE USER ai_readonly
WITH PASSWORD 'A_STRONG_PRIVATE_PASSWORD';

GRANT CONNECT
ON DATABASE organization_database
TO ai_readonly;

GRANT USAGE
ON SCHEMA public
TO ai_readonly;

GRANT SELECT
ON ALL TABLES IN SCHEMA public
TO ai_readonly;

GRANT SELECT
ON ALL SEQUENCES IN SCHEMA public
TO ai_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO ai_readonly;
```

If the organization uses a schema other than `public`, replace every occurrence of `public` with the correct schema name.

The account must not receive these privileges:

```text
INSERT
UPDATE
DELETE
TRUNCATE
CREATE
ALTER
DROP
```

## 6. Verify Network Access

From the Windows deployment host, run:

```powershell
Test-NetConnection DATABASE_HOST -Port 5432
```

Expected result:

```text
TcpTestSucceeded : True
```

If it returns `False`, the IT team must check:

- VPN connectivity
- Windows Firewall
- Server firewall rules
- PostgreSQL `listen_addresses`
- PostgreSQL `pg_hba.conf`
- IP allowlisting

Only the deployment host IP should be allowed where practical.

## 7. Create the Environment File

From the project root:

```powershell
Copy-Item .env.example .env
notepad .env
```

Add or update these values:

```env
APP_NAME=Persian AI Data Analyst
APP_VERSION=0.1.0
DEBUG=false

EXTERNAL_DATABASE_URL=postgresql://ai_readonly:PASSWORD@DATABASE_HOST:5432/DATABASE_NAME
EXTERNAL_DATABASE_HOST=DATABASE_HOST
EXTERNAL_DATABASE_PORT=5432
EXTERNAL_DATABASE_NAME=DATABASE_NAME
EXTERNAL_DATABASE_USER=ai_readonly
EXTERNAL_DATABASE_PASSWORD=PASSWORD

CHROMA_PORT=8001

LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal
OLLAMA_PORT=11434
OLLAMA_MODEL=gemma3:12b
OLLAMA_TIMEOUT=180
OLLAMA_TEMPERATURE=0.1
OLLAMA_TOP_P=0.9

LLM_CONTEXT_MAX_TOKENS=8192
LLM_RESERVED_OUTPUT_TOKENS=1024
LLM_TOKENIZER_MODEL_PATH=

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_URL=https://api.openai.com/v1/chat/completions

TENANT_ID=organization
EMBEDDING_MODEL_PATH=./models/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DEVICE=cpu

API_HOST=0.0.0.0
API_PORT=8080
```

Database credentials must be entered locally by authorized IT staff. Do not send credentials by email or messaging applications, and never commit `.env` to Git.

If the password contains characters such as `@`, `:`, `/`, `#`, `%`, or `?`, the password portion of `EXTERNAL_DATABASE_URL` must be URL-encoded.

For SSL-enabled PostgreSQL, use:

```env
EXTERNAL_DATABASE_URL=postgresql://ai_readonly:PASSWORD@DATABASE_HOST:5432/DATABASE_NAME?sslmode=require
```

## 8. Create the External Database Compose Override

Create this file in the project root:

```text
docker-compose.external.yml
```

Use the following content:

```yaml
services:
  api:
    environment:
      DATABASE_URL: ${EXTERNAL_DATABASE_URL}
      DATABASE_HOST: ${EXTERNAL_DATABASE_HOST}
      DATABASE_PORT: ${EXTERNAL_DATABASE_PORT}
      DATABASE_NAME: ${EXTERNAL_DATABASE_NAME}
      DATABASE_USER: ${EXTERNAL_DATABASE_USER}
      DATABASE_PASSWORD: ${EXTERNAL_DATABASE_PASSWORD}
```

## 9. Validate the Docker Configuration

Run:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  config
```

Inspect the API environment and confirm that the database host is the organization's PostgreSQL server, not `postgres:5432`.

Warning: `docker compose config` may display the resolved password. Do not copy, record, or share its output.

## 10. Build and Start the System

Build the API image:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  build api
```

Do not use `--no-cache` during normal builds.

Start the services:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  up -d
```

Check their status:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  ps
```

## 11. Verify the Database Target Without Displaying the Password

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  exec api python -c "from backend.config import get_settings; s=get_settings(); print(s.database_host, s.database_port, s.database_name, s.database_user)"
```

The command must display the external PostgreSQL host, port, database name, and read-only user.

## 12. Test the Database Connection

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  exec api python -c "from backend.database.connection import engine; c=engine.connect(); print('DATABASE CONNECTED'); c.close()"
```

Expected result:

```text
DATABASE CONNECTED
```

Common errors:

| Error | Likely cause |
|---|---|
| Connection refused | Host, port, firewall, or PostgreSQL listener |
| Password authentication failed | Incorrect user or password |
| No pg_hba.conf entry | Deployment host IP is not allowed |
| SSL required | Add `?sslmode=require` |
| Permission denied | Missing schema or table grants |

## 13. Verify the API and Ollama

View API logs:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  logs --tail 200 api
```

Check API health:

```powershell
Invoke-RestMethod http://localhost:8080/health
```

Expected values:

```text
status           : ok
llm_enabled      : True
ollama_connected : True
```

Open the dashboard:

```text
http://localhost:8080/dashboard
```

## 14. Discover the New Database

In the administration panel, perform these steps in order:

```text
Read Database Information
→ Review Table and Column Meanings
→ Register Semantic Corrections
→ Run Database Health Check
→ Run Full System Update
→ Synchronize Groups and Reports
→ Check Semantic Status
```

The final semantic status must be:

```text
up_to_date
```

## 15. Define the Allowed Data Scope

An authorized database expert must classify tables and columns as:

- Allowed for analysis
- Allowed with restrictions
- Confidential
- Internal/system-only

Sensitive fields such as credentials, financial account details, private contact data, health data, or security tokens must be excluded or masked.

## 16. Validate Table Meanings and Relationships

The client's database expert must confirm:

- Persian business meaning of every allowed table
- Persian aliases for important columns
- Primary and foreign keys
- Correct join paths
- Valid business status values
- Value mappings between Persian terms and stored values
- Official KPI definitions
- Required filters and access limitations

Changing only `DATABASE_URL` is not sufficient. Database semantics and relationships must be reviewed before business use.

## 17. Create the Organization Tenant

Create an organization-specific knowledge directory:

```text
knowledge/tenants/organization/
├── groups/
└── reports/
```

The directory name must match:

```env
TENANT_ID=organization
```

Groups should describe business domains such as employees, customers, sales, requests, inventory, or finance. Reports should define approved metrics, dimensions, filters, joins, and output columns.

## 18. Run Validation and Benchmarks

Prepare representative questions covering:

- Total record counts
- Single-column filters
- Multi-column filters
- Record lookup by identifier
- Minimum and maximum values
- Sum and average
- Grouping and sorting
- Multi-table joins
- Missing records
- Ambiguous requests
- Unauthorized or unsafe requests

Run:

- Retrieval Benchmark
- SQL Regression Benchmark
- Safety Evaluation
- End-to-End Evaluation

For critical questions, compare the generated result with SQL approved by the database administrator or business analyst.

## 19. Production Acceptance

Before production use, confirm:

- The PostgreSQL account is read-only.
- Only approved schemas, tables, and columns are available.
- Semantic status is `up_to_date`.
- Join paths have been reviewed.
- Official KPI calculations have been validated.
- Benchmark results meet the agreed threshold.
- Sensitive fields are excluded or masked.
- API, SQL, token, latency, and error events are audited.
- Backup and recovery procedures are documented.

## 20. Operational Commands

View status:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  ps
```

View resource usage:

```powershell
docker stats --no-stream
```

Restart only the API:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  restart api
```

Apply a code update:

```powershell
git pull
docker compose `
  -f docker-compose.yml `
  -f docker-compose.external.yml `
  up -d --build api
```

Do not run the following command without a verified backup:

```powershell
docker compose down -v
```

It deletes Docker volumes and may remove local PostgreSQL and ChromaDB data.

## Responsibility and Credential Policy

The software provider does not require the organization's database password. Authorized client IT personnel must create the read-only account and enter all credentials locally on the deployment host.

The client database administrator or business data owner is responsible for confirming table meanings, relationships, sensitive fields, and official report definitions.
