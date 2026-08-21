محصول فعلی از نظر RAG و Text-to-SQL قوی است، ولی برای تبدیل‌شدن به یک محصول Production-ready سه خلأ اصلی دارد:
مدیریت استاندارد مدل و Token
استقرار و زیرساخت Production
پایش و ارزیابی LLM در محیط واقعی
معماری پیشنهادی نهایی
UI
 ↓
FastAPI
 ├── Authentication / Rate Limit
 ├── Query Pipeline
 │    ├── Intent Detection
 │    ├── Retrieval
 │    │    ├── Embedding Model
 │    │    ├── ChromaDB
 │    │    ├── Hybrid Search
 │    │    └── Reranker
 │    ├── Context Builder
 │    ├── Model Router
 │    │    ├── Ollama
 │    │    └── OpenAI
 │    ├── SQL Validator
 │    └── PostgreSQL
 │
 ├── Redis
 │    ├── Cache
 │    ├── Rate Limit
 │    └── Background Jobs
 │
 └── Observability
      ├── Token/Cost Tracking
      ├── Retrieval Evaluation
      ├── User Feedback
      ├── PostHog
      └── Logs/Metrics
چه چیزهایی را همین حالا اضافه کنیم؟
اولویت ۱: Token Counter و Context Budget
این قابلیت باید اضافه شود؛ چون اکنون Context را می‌سازیم ولی دقیقاً نمی‌دانیم چند Token وارد مدل شده است.
محل پیشنهادی:
backend/llm/
├── token_counter.py
├── context_budget.py
└── models.py
ساختار اولیه:
from dataclasses import dataclass


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


class TokenCounter:
    def count(self, text: str) -> int:
        raise NotImplementedError
برای Hugging Face:
from transformers import AutoTokenizer


class HuggingFaceTokenCounter:
    def __init__(self, model_path: str):
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path
        )

    def count(self, text: str) -> int:
        tokens = self.tokenizer.encode(
            text,
            add_special_tokens=True,
        )

        return len(tokens)
و Context Budget:
class ContextBudget:
    def __init__(
        self,
        maximum_tokens: int,
        reserved_output_tokens: int,
    ):
        self.maximum_tokens = maximum_tokens
        self.reserved_output_tokens = (
            reserved_output_tokens
        )

    @property
    def available_input_tokens(self) -> int:
        return (
            self.maximum_tokens
            - self.reserved_output_tokens
        )
این قابلیت باید قبل از ارسال Prompt اعمال شود:
Context Builder
→ Token Counter
→ Context Trimming
→ LLM
اولویت: خیلی بالا
اولویت ۲: Provider مستقل برای مدل‌ها
اکنون llm_service.py مستقیماً به Ollama وابسته است. بهتر است Pipeline نداند مدل از کجا اجرا می‌شود.
ساختار پیشنهادی:
backend/llm/
├── base.py
├── ollama_provider.py
├── openai_provider.py
├── router.py
└── models.py
Interface مشترک:
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        pass
Ollama:
class OllamaProvider(LLMProvider):
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        # تماس با localhost:11434
        ...
OpenAI:
class OpenAIProvider(LLMProvider):
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        # تماس با OpenAI API
        ...
بعد Pipeline فقط این را می‌بیند:
provider = model_router.select(request)

answer = await provider.generate(prompt)
مزایا:
امکان تغییر Ollama به OpenAI
امکان مقایسه مدل‌ها
امکان fallback
پایه‌ی Model Routing
تست‌پذیری بهتر
اولویت: خیلی بالا
اولویت ۳: Model Routing
بعد از جداکردن Providerها اضافه می‌شود.
محل:
backend/llm/router.py
نمونه:
class ModelRouter:
    def select(self, request) -> str:
        if request.contains_sensitive_data:
            return "ollama"

        if request.task == "simple_classification":
            return "small_local_model"

        if request.task == "complex_reasoning":
            return "openai"

        return "ollama"
در محصول واقعی Route باید براساس Policy انتخاب شود:
حساسیت داده
هزینه
پیچیدگی سؤال
زمان پاسخ
سلامت Provider
دقت تاریخی مدل
نکته مهم: تا زمانی که فقط Ollama داریم، Router پیچیده ارزش زیادی ندارد. ابتدا Provider abstraction را می‌سازیم.
اولویت: بالا، بعد از Provider
اولویت ۴: Token، Cost و Latency Tracking
اکنون SQL Audit و Retrieval Benchmark داریم؛ اما باید مصرف مدل هم ثبت شود.
محل:
backend/observability/
├── llm_events.py
├── cost_calculator.py
├── metrics.py
└── redaction.py
رویداد پیشنهادی:
class LLMEvent:
    query_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost: float
    success: bool
ثبت درخواست:
event = LLMEvent(
    query_id=query_id,
    provider="ollama",
    model="qwen2.5:7b",
    input_tokens=1250,
    output_tokens=130,
    latency_ms=820,
    estimated_cost=0.0,
    success=True,
)
برای مدل محلی بهتر است علاوه بر هزینه API، زمان و منابع را هم بسنجیم:
Latency
CPU/GPU time
Memory
Queue time
اولویت: خیلی بالا
اولویت ۵: توسعه Evaluation و DeepEval
اکنون دو معیار داخلی داریم:
Regression Benchmark
Retrieval Benchmark
این پایه بسیار خوب است، اما باید Evaluation را به چند سطح تقسیم کنیم:
Retrieval Evaluation
SQL Evaluation
Answer Evaluation
Safety Evaluation
End-to-End Evaluation
ساختار پیشنهادی:
backend/evaluation/
├── datasets/
├── retrieval_evaluator.py
├── sql_evaluator.py
├── answer_evaluator.py
├── safety_evaluator.py
└── runner.py
سنجه‌ها:
{
    "retrieval_top1": 0.83,
    "retrieval_mrr": 0.91,
    "sql_exact_match": 0.87,
    "sql_execution_accuracy": 0.94,
    "answer_groundedness": 0.92,
    "unsafe_query_rejection": 1.0,
}
DeepEval را می‌توان به‌عنوان Adapter اضافه کرد:
evaluation/
├── internal/
└── deepeval_adapter.py
نباید ارزیابی فعلی را حذف کنیم. DeepEval باید مکمل باشد، چون معیارهای SQL اختصاصی سیستم را ابزار عمومی به‌خوبی نمی‌شناسد.
اولویت: خیلی بالا
چه چیزهایی را برای Production اضافه کنیم؟
اولویت ۶: Dockerfile برای خود API
اکنون PostgreSQL و ChromaDB داخل Docker هستند، ولی FastAPI هنوز بیرون Docker اجرا می‌شود.
باید اضافه شود:
Dockerfile
نمونه:
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY knowledge ./knowledge
COPY schema ./schema

CMD [
  "python",
  "-m",
  "uvicorn",
  "backend.api.main:app",
  "--host",
  "0.0.0.0",
  "--port",
  "8080"
]
سپس Compose:
services:
  api:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
      chromadb:
        condition: service_healthy
معماری بعدی:
Docker Compose
├── API
├── PostgreSQL
├── ChromaDB
└── Redis
اولویت: خیلی بالا برای Deployment
اولویت ۷: Redis
Redis در نسخه‌ی تک‌کاربره ضروری نیست، ولی برای محصول چندکاربره مفید است.
محل پیشنهادی:
backend/cache/
├── redis_client.py
├── embedding_cache.py
├── query_cache.py
└── keys.py
کاربرد اول: Cache کردن Embedding:
async def get_embedding(text: str):
    key = hash_text(text)

    cached = await redis.get(
        f"embedding:{key}"
    )

    if cached:
        return json.loads(cached)

    vector = embedding_service.embed_text(text)

    await redis.set(
        f"embedding:{key}",
        json.dumps(vector),
        ex=86400,
    )

    return vector
کاربرد دوم: Rate Limiting:
rate-limit:{tenant}:{user}
کاربرد سوم: Job Lock:
semantic-sync:{tenant}:lock
کاربرد چهارم: صف Benchmark و Syncهای طولانی.
نکته: نباید جواب‌های حساس دیتابیس را بدون Policy داخل Cache ذخیره کنیم.
اولویت: متوسط؛ هنگام چندکاربره‌شدن
اولویت ۸: Background Worker
عملیات زیر ممکن است طولانی باشند:
Sync کردن Embedding
Semantic Discovery
Benchmark
Index Rebuild
Incremental Update
اکنون این کارها داخل API اجرا می‌شوند. در Production بهتر است Worker جدا داشته باشیم:
API
 ↓
Job Queue
 ↓
Worker
می‌توان از این ابزارها استفاده کرد:
Redis + RQ
Redis + Celery
Redis + Dramatiq
نمونه:
job_id = queue.enqueue(
    run_semantic_sync,
    tenant_id,
)
API سریع پاسخ می‌دهد:
{
  "job_id": "sync-123",
  "status": "queued"
}
اولویت: متوسط رو به بالا
اولویت ۹: Authentication و Authorization
قبل از Cloud از Redis و حتی LangGraph مهم‌تر است.
اکنون باید مشخص شود:
چه کسی می‌تواند سؤال بپرسد؟
چه کسی کد ملی ببیند؟
چه کسی Schema را Sync کند؟
چه کسی Semantic Review انجام دهد؟
چه کسی Benchmark اجرا کند؟
ساختار:
backend/auth/
├── models.py
├── service.py
├── dependencies.py
└── permissions.py
سطوح دسترسی:
PERMISSIONS = {
    "viewer": {
        "query",
    },
    "analyst": {
        "query",
        "view_sql",
        "export",
    },
    "admin": {
        "query",
        "sync_schema",
        "review_semantics",
        "run_benchmark",
    },
}
برای محصول سازمانی، این مورد ضروری است.
اولویت: بحرانی
Analytics و PostHog را کجا اضافه کنیم؟
PostHog
PostHog باید رخدادهای محصول را ببیند، نه داده‌های حساس را.
محل:
backend/analytics/
├── events.py
├── posthog_client.py
└── privacy.py
رخداد مجاز:
capture(
    user_id=hashed_user_id,
    event="query_completed",
    properties={
        "intent": "count",
        "group": "student",
        "latency_ms": 850,
        "success": True,
        "feedback": "positive",
    },
)
رخداد نامجاز:
{
    "question": "اطلاعات کارمند با کد ملی 8223876400"
}
نباید سؤال خام، کد ملی، نام شخص، SQL حساس یا نتیجه دیتابیس به سرویس Analytics ارسال شود.
اگر حریم خصوصی سازمان مهم است:
PostHog را Self-host کنیم.
یا فقط Metrics ناشناس ارسال کنیم.
یا از Prometheus/Grafana استفاده کنیم.
اولویت: متوسط، بعد از Privacy Policy
Cloud کجا وارد سیستم می‌شود؟
Cloud یک ماژول داخل backend نیست؛ محل اجرای کل محصول است.
ساختار Deployment پیشنهادی:
Cloud
├── API Container
├── Worker Container
├── Managed PostgreSQL
├── Redis
├── Vector Database
├── Secret Manager
├── Object Storage
└── Monitoring
مسیر پیشنهادی AWS
FastAPI       → ECS Fargate
PostgreSQL    → RDS PostgreSQL
Redis         → ElastiCache
Files         → S3
Secrets       → Secrets Manager
Logs          → CloudWatch
مسیر پیشنهادی GCP
FastAPI       → Cloud Run
PostgreSQL    → Cloud SQL
Redis         → Memorystore
Files         → Cloud Storage
Secrets       → Secret Manager
Logs          → Cloud Logging
برای اولین Deployment، من GCP Cloud Run را ساده‌تر می‌دانم؛ اما اگر بازار کار مدنظر تو بیشتر AWS است، ECS و RDS ارزش آموزشی بیشتری دارند.
اولویت: بعد از Docker، Auth و Observability
LangGraph را کجا اضافه کنیم؟
Pipeline فعلی پیچیده است، اما همین حالا هم کار می‌کند. بازنویسی کامل آن با LangGraph ریسک بالایی دارد.
راه درست: ابتدا یک Workflow کوچک آزمایشی بسازیم.
محل:
backend/workflows/
├── state.py
├── query_graph.py
└── nodes/
    ├── retrieve.py
    ├── plan_sql.py
    ├── validate.py
    ├── repair.py
    └── execute.py
State:
class QueryState(TypedDict):
    question: str
    context: dict
    sql: str | None
    validation_errors: list[str]
    repair_attempts: int
    result: dict | None
Graph:
Retrieve
   ↓
Generate SQL
   ↓
Validate ── invalid ──→ Repair
   │                      │
 valid ←──────────────────┘
   ↓
Execute
LangGraph زمانی واقعاً ارزش دارد که:
شاخه‌های متعدد داریم.
State بین مراحل حفظ می‌شود.
Repair Loop داریم.
Human Approval داریم.
Resume کردن Workflow لازم است.
محصول ما این شرایط را تا حدی دارد؛ پس LangGraph مناسب است، ولی باید به‌صورت Adapter و مرحله‌ای اضافه شود.
اولویت: متوسط؛ آزمایشی، نه بازنویسی کامل
MCP را کجا اضافه کنیم؟
MCP باید در مرز سیستم قرار بگیرد، نه در هسته‌ی SQL Pipeline.
External AI Agent
       ↓ MCP
Persian Data Analyst
       ↓
Safe Services
ساختار:
backend/mcp/
├── server.py
├── tools.py
└── resources.py
ابزارهای مناسب:
get_safe_schema
search_reports
ask_data_question
get_query_status
run_retrieval_benchmark
ابزار نامناسب:
execute_any_sql
نمونه مفهومی:
@mcp.tool()
async def ask_data_question(
    question: str,
) -> dict:
    return await query_pipeline.execute(
        PipelineRequest(
            question=question,
            execute=True,
        )
    )
MCP کمک می‌کند محصول ما توسط Agentهای دیگر استفاده شود. برای UI فعلی ضروری نیست.
اولویت: پایین تا متوسط؛ برای Integration
Fine-tuning را کجا اضافه کنیم؟
فعلاً نباید به Runtime اصلی اضافه شود.
اگر روزی داده آموزشی کافی داشتیم، باید پروژه‌ی جداگانه داشته باشد:
training/
├── datasets/
├── prepare_dataset.py
├── train_lora.py
├── evaluate_model.py
├── configs/
└── artifacts/
Dataset:
{
  "instruction": "برای سؤال زیر SQL تولید کن",
  "input": "تعداد دانش‌آموزان تهران",
  "output": "SELECT COUNT(*) ..."
}
مدل آموزش‌دیده فقط در صورت عبور از benchmark وارد محصول می‌شود:
Train
→ Offline Evaluation
→ Safety Evaluation
→ Compare with Current Model
→ Model Registry
→ Controlled Deployment
Fine-tuning را نباید برای یاددادن رکوردهای دیتابیس استفاده کنیم؛ رکوردها تغییر می‌کنند و باید با RAG/SQL خوانده شوند.
اولویت محصول: فعلاً پایین
اولویت آموزشی: مهم
Hugging Face کجا توسعه پیدا کند؟
مدل Embedding فعلی از Hugging Face ecosystem می‌آید. برای معماری بهتر می‌توانیم یک Model Registry محلی بسازیم:
backend/models/
├── registry.py
├── embedding_factory.py
└── metadata.py
مثال:
MODELS = {
    "multilingual-mpnet": {
        "type": "embedding",
        "path": "./models/paraphrase-multilingual-mpnet-base-v2",
        "dimension": 768,
        "languages": ["fa", "en"],
    }
}
این کار تغییر مدل Embedding و مقایسه آن‌ها را ساده می‌کند.
اولویت: متوسط
AWS و GCP را هم‌زمان اضافه کنیم؟
خیر.
کد برنامه باید Cloud-agnostic باشد:
Application Code
      ↓
Docker Image
      ↓
AWS یا GCP
ولی فایل‌های Deployment می‌توانند جدا باشند:
deploy/
├── local/
│   └── docker-compose.yml
├── aws/
│   └── terraform/
└── gcp/
    └── terraform/
برای یادگیری هر دو را بررسی می‌کنیم، اما برای محصول ابتدا فقط یکی را انتخاب می‌کنیم.
ترتیب پیشنهادی اعمال تغییرات
فاز P0 — ضروری و کم‌ریسک
Token Counter
Context Budget
LLM Provider Interface
Ollama Provider
Token/Latency Audit
توسعه Evaluation Dataset
این‌ها مستقیماً کیفیت و قابلیت‌اندازه‌گیری سیستم را بهتر می‌کنند.
فاز P1 — آماده‌سازی Production
Dockerfile برای API
Health Check کامل
Authentication و Role-Based Access
Secret Management
Structured Logging
Backup/Restore Runbook
فاز P2 — مقیاس‌پذیری
Redis
Embedding Cache
Rate Limiting
Background Worker
Job Status API
فاز P3 — LLMOps
Provider Registry
OpenAI Provider اختیاری
Model Routing
Cost Governance
DeepEval Adapter
Analytics امن
Dashboard کیفیت مدل
فاز P4 — Agent Integration
LangGraph آزمایشی
Human Approval Node
MCP Server
MCP Tools امن
فاز P5 — Cloud
انتخاب AWS یا GCP
Container Deployment
Managed PostgreSQL
Managed Redis
Secret Manager
Monitoring
Scaling و Disaster Recovery
فاز P6 — Fine-tuning آزمایشی
Dataset Versioning
LoRA Training
ارزیابی مدل Fine-tuned
مقایسه با RAG و مدل اصلی
انتشار فقط در صورت برتری قابل‌اندازه‌گیری
چیزهایی که فعلاً نباید اضافه کنیم
برای جلوگیری از پیچیدگی بی‌دلیل، این موارد را فوراً وارد هسته نمی‌کنیم:
Fine-tuning برای داده‌های دیتابیس
Kubernetes
پشتیبانی هم‌زمان AWS و GCP
بازنویسی کامل Pipeline با LangGraph
ارسال سؤال خام کاربران به PostHog
Redis فقط برای اینکه نام Redis در رزومه باشد
MCP Tool با امکان اجرای SQL آزاد
چند مدل بدون Benchmark و Routing Policy
پیشنهاد نهایی
قبل از اپیزود ۴، بهترین کار این نیست که همه فناوری‌ها را پیاده کنیم. آن‌ها را در طول آموزش، روی همین محصول اضافه می‌کنیم:
اپیزود آموزشی
→ فهم مفهوم
→ پیاده‌سازی کوچک
→ تست
→ اتصال به محصول
→ Benchmark
اولین بسته‌ی منطقی برای اضافه‌شدن به محصول این است:
Token Counter
+ Context Budget
+ LLM Provider Abstraction
+ Token/Latency Audit
این بسته هم آموزشی است، هم واقعاً محصول را بهتر می‌کند و پایه‌ی OpenAI API، Model Routing و Cost Governance خواهد بود.


12:53 AM