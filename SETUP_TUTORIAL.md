# Persian AI Data Analyst - Complete Setup Tutorial

## Overview

This tutorial will guide you through setting up and running the Persian AI Data Analyst system from scratch.

## Prerequisites

- Windows 10/11
- Python 3.12 (not hermes venv)
- Docker Desktop
- Internet connection (for initial setup only)

## Step 1: Install Python 3.12

1. Download Python 3.12 from https://www.python.org/downloads/
2. During installation, check "Add Python to PATH"
3. Verify installation:
```powershell
python --version
# Should show: Python 3.12.x
```

## Step 2: Install Docker Desktop

1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Install and restart your computer
3. Verify installation:
```powershell
docker --version
docker-compose --version
```

## Step 3: Install Ollama

1. Download Ollama from https://ollama.ai
2. Install Ollama
3. Start Ollama service:
```powershell
ollama serve
```

4. Pull the required model (in a new terminal):
```powershell
ollama pull qwen2.5:7b
```

5. Verify Ollama is working:
```powershell
ollama list
# Should show: qwen2.5:7b
```

## Step 4: Clone the Project

```powershell
cd D:\projects
git clone <repository-url>
cd "LLM Database"
```

## Step 5: Install Python Dependencies

```powershell
# Use Python 3.12 explicitly
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

## Step 6: Configure Environment

```powershell
# Copy the environment template
copy .env.example .env

# Edit .env if needed (defaults work for most setups)
notepad .env
```

## Step 7: Start Docker Services

```powershell
# Start PostgreSQL and ChromaDB
docker-compose up -d

# Verify services are running
docker-compose ps
```

Wait for services to be healthy (about 30 seconds).

## Step 8: Initialize Database

```powershell
# Create the education database tables
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -c "
from sqlalchemy import create_engine, text
from pathlib import Path

engine = create_engine('postgresql://postgres:postgres@localhost:5433/persian_ai_db')
sql_file = Path('database_scripts/init_education.sql')
with open(sql_file, encoding='utf-8') as f:
    sql = f.read()
with engine.connect() as conn:
    conn.execute(text(sql))
    conn.commit()
print('Database initialized!')
"
```

## Step 9: Sync Knowledge and Reports

```powershell
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -c "
import sys
sys.path.insert(0, '.')
from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever

g = group_retriever.sync_groups('education_ministry')
r = report_retriever.sync_reports('education_ministry')
print(f'Synced: {g} groups, {r} reports')
"
```

## Step 10: Start the API Server

```powershell
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
```

## Step 11: Verify Installation

### Check API Health
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/health"
```

### Open Dashboard
```
http://localhost:8080/dashboard
```

### Test a Query
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/query" -Method POST -ContentType "application/json" -Body '{"question":"تعداد دانش\u200cآموزان فعال"}'
```

## Step 12: Run Tests

```powershell
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_api.py -v
```

## Troubleshooting

### Port 8080 already in use
```powershell
# Find and kill the process
netstat -ano | findstr :8080
taskkill /PID <PID> /F
```

### Docker services not starting
```powershell
# Check Docker status
docker-compose ps

# Restart services
docker-compose down
docker-compose up -d
```

### Ollama not responding
```powershell
# Check Ollama status
ollama list

# Restart Ollama
ollama serve
```

### Python module not found
```powershell
# Use Python 3.12 explicitly
& "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/dashboard` | Web dashboard |
| POST | `/query` | Ask questions in Persian |
| POST | `/reports/sync` | Sync report data |
| POST | `/reports/search` | Search for reports |
| GET | `/knowledge/context` | Get business knowledge |

## Example Queries

```powershell
# Student queries
Invoke-RestMethod -Uri "http://localhost:8080/query" -Method POST -ContentType "application/json" -Body '{"question":"تعداد دانش\u200cآموزان فعال"}'

# Salary queries
Invoke-RestMethod -Uri "http://localhost:8080/query" -Method POST -ContentType "application/json" -Body '{"question":"میانگین حقوق خالص کارکنان"}'

# Employee queries
Invoke-RestMethod -Uri "http://localhost:8080/query" -Method POST -ContentType "application/json" -Body '{"question":"لیست مدیران مدارس"}'

# Safety test (should be rejected)
Invoke-RestMethod -Uri "http://localhost:8080/query" -Method POST -ContentType "application/json" -Body '{"question":"حذف رکوردهای حقوق"}'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | http://localhost | Ollama server URL |
| `OLLAMA_PORT` | 11434 | Ollama port |
| `OLLAMA_MODEL` | qwen2.5:7b | LLM model name |
| `DATABASE_PORT` | 5433 | PostgreSQL port |
| `CHROMA_PORT` | 8001 | ChromaDB port |
| `TENANT_ID` | education_ministry | Active tenant |
| `EMBEDDING_MODEL_PATH` | models/paraphrase-multilingual-mpnet-base-v2 | Embedding model path |

## Architecture

```
User Question (Persian)
    ↓
Safety Check (reject destructive ops)
    ↓
Multi-Intent Detection
    ↓
Ambiguity Detection
    ↓
Group Retrieval (ChromaDB)
    ↓
Report Retrieval (ChromaDB)
    ↓
SQL Planning
    ↓
SQL Generation (Ollama)
    ↓
SQL Validation
    ↓
SQL Execution (PostgreSQL)
    ↓
Answer Generation (Ollama)
    ↓
Persian Response
```
