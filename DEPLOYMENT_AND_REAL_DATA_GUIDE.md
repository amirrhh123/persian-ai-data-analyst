# راهنمای انتقال و اتصال به داده واقعی

## ۱) اجرای همین سیستم روی یک سیستم دیگر

### پیش‌نیازها

- نصب Docker Desktop و فعال بودن Docker Compose
- حداقل ۸GB RAM (برای اجرای مدل محلی بیشتر توصیه می‌شود)
- دسترسی شبکه برای دانلود imageها و Python packageها
- در صورت استفاده از Ollama: نصب Ollama و دریافت مدل انتخابی

### انتقال پروژه

1. مخزن را clone کنید:

```bash
git clone https://github.com/amirrhh123/persian-ai-data-analyst.git
cd persian-ai-data-analyst
```

2. فایل تنظیمات را بسازید:

```bash
copy .env.example .env     # Windows
cp .env.example .env      # Linux/macOS
```

3. مقادیر `.env` را برای محیط مقصد تنظیم کنید؛ رمزها را در Git commit نکنید. نمونه کامل برای اجرای Docker محلی:

```env
APP_NAME=Persian AI Data Analyst
APP_VERSION=0.1.0
DEBUG=false

DATABASE_NAME=persian_ai_db
DATABASE_USER=postgres
DATABASE_PASSWORD=یک_رمز_قوی
DATABASE_PORT=5433

CHROMA_PORT=8001

LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal
OLLAMA_PORT=11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT=120
OLLAMA_TEMPERATURE=0.1
OLLAMA_TOP_P=0.9
LLM_CONTEXT_MAX_TOKENS=8192
LLM_RESERVED_OUTPUT_TOKENS=1024
LLM_TOKENIZER_MODEL_PATH=

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_URL=https://api.openai.com/v1/chat/completions

TENANT_ID=education_ministry
EMBEDDING_MODEL_PATH=./models/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DEVICE=cpu

API_HOST=0.0.0.0
API_PORT=8080
```

در حالت Docker، Compose آدرس داخلی صحیح را خودش به API می‌دهد: PostgreSQL با `postgres:5432` و ChromaDB با `chromadb:8000`. مقادیر `localhost:5433` و `localhost:8001` فقط برای دسترسی از خود ویندوز هستند.

4. سرویس‌ها را build و اجرا کنید:

```bash
docker compose up -d --build
```

قبل از build مطمئن شوید پوشه مدل وجود دارد:

```text
models/paraphrase-multilingual-mpnet-base-v2/
```

این پوشه به‌صورت read-only داخل کانتینر در `/app/models` mount می‌شود و وزن مدل وارد GitHub نمی‌شود.

برای جلوگیری از دانلود بسته‌های CUDA، build محلی از wheel نسخه CPU استفاده می‌کند. قبل از build این فایل باید موجود باشد:

```text
docker_wheels/torch-2.12.1+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
```

این فایل حجیم در GitHub نگهداری نمی‌شود. در سیستم مقصد یا آن را از سیستم مبدأ کپی کنید، یا نسخه CPU سازگار با Python 3.12 و Linux را از منبع رسمی PyTorch دریافت و نام/مسیر Dockerfile را متناسب با آن اصلاح کنید.

فایل `docker-constraints.txt` نسخه‌های `torch` و `torchvision` را با هم قفل می‌کند. این فایل را حذف نکنید؛ در غیر این صورت pip ممکن است `torchvision` جدید را انتخاب کند، PyTorch را ارتقا دهد و دوباره بسته‌های حجیم CUDA/NVIDIA را دانلود کند.

نسخه فعلی `chroma-hnswlib` برای Python 3.12 ممکن است wheel آماده نداشته باشد. Dockerfile به‌طور موقت `build-essential` را برای کامپایل آن نصب می‌کند و بعد از نصب حذف می‌کند؛ بنابراین compiler وارد image نهایی نمی‌شود. نصب PyTorch در یک Docker layer جداست تا اگر مرحله Chroma خطا داد، دانلود و نصب Torch در build بعدی از cache تکرار نشود.

Docker BuildKit برای pip یک cache پایدار دارد. اگر دانلود یک package با خطای timeout یا hash mismatch متوقف شد، build را دوباره با `docker compose build api` اجرا کنید؛ فایل‌های سالم قبلی دوباره دانلود نمی‌شوند. استفاده از `--no-cache` این مزیت را از بین می‌برد و فقط هنگام عیب‌یابی ویژه توصیه می‌شود.

5. وضعیت سرویس‌ها را بررسی کنید:

```bash
docker compose ps
docker compose logs -f api
```

6. سلامت API را بررسی کنید:

```bash
curl http://localhost:8080/health
```

### انتقال داده‌های Docker

داده PostgreSQL و ChromaDB در volumeها ذخیره می‌شوند. برای انتقال دائمی، روی سیستم مبدأ backup بگیرید:

```bash
docker compose exec postgres pg_dump -U postgres -d persian_ai_db > backup.sql
```

در مقصد، پس از بالا آمدن PostgreSQL، restore کنید:

```bash
docker compose exec -T postgres psql -U postgres -d persian_ai_db < backup.sql
```

سپس semantic layer و indexهای ChromaDB را دوباره sync کنید.

### مدل Ollama

مدل داخل image API قرار ندارد. روی سیستم مقصد جداگانه نصب کنید:

```bash
ollama pull qwen2.5:7b
```

اگر API داخل Docker و Ollama روی host است، تنظیمات زیر را نگه دارید:

```env
OLLAMA_HOST=http://host.docker.internal
OLLAMA_PORT=11434
```

## ۲) اتصال به PostgreSQL واقعی

### حالت پیشنهادی: اتصال شبکه‌ای مستقیم

در `.env` مقصد این مقادیر را تنظیم کنید:

```env
DATABASE_HOST=db.company.local
DATABASE_PORT=5432
DATABASE_NAME=production_db
DATABASE_USER=readonly_analyst
DATABASE_PASSWORD=یک_رمز_قوی
DATABASE_URL=postgresql://readonly_analyst:رمز@db.company.local:5432/production_db
```

نکته: Compose اصلی برای دیتابیس آزمایشی داخلی طراحی شده و `DATABASE_URL` داخلی تولید می‌کند. برای دیتابیس واقعی یک فایل `docker-compose.production.yml` بسازید:

```yaml
services:
  api:
    environment:
      DATABASE_URL: ${DATABASE_URL}
      DATABASE_HOST: ${DATABASE_HOST}
      DATABASE_PORT: ${DATABASE_PORT}
      DATABASE_NAME: ${DATABASE_NAME}
      DATABASE_USER: ${DATABASE_USER}
      DATABASE_PASSWORD: ${DATABASE_PASSWORD}
    depends_on:
      chromadb:
        condition: service_healthy
```

سپس اجرا کنید:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build api chromadb
```

اگر رمز شامل `@`، `:`، `/` یا `#` است، آن را در `DATABASE_URL` به‌شکل URL-encoded وارد کنید.

برای امنیت، کاربر فقط خواندنی بسازید:

```sql
CREATE USER readonly_analyst WITH PASSWORD 'strong-password';
GRANT CONNECT ON DATABASE production_db TO readonly_analyst;
GRANT USAGE ON SCHEMA public TO readonly_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO readonly_analyst;
```

اتصال را از داخل کانتینر تست کنید:

```bash
docker compose exec api python -c "from backend.database.connection import engine; c=engine.connect(); print('database connected'); c.close()"
```

### نکات امنیتی دیتابیس

- از حساب owner یا superuser در API استفاده نکنید.
- دسترسی شبکه را فقط به IP سرور API محدود کنید.
- SSL دیتابیس را در محیط سازمانی فعال کنید.
- رمزها را در `.env` محلی یا Secret Manager نگه دارید، نه در Git.
- برای API واقعی، connection pool و timeout تنظیم کنید.

## ۳) اتصال به جدول‌های واقعی

1. ابتدا schema و جدول‌ها را با ابزار بررسی ساختار دیتابیس بخوانید.
2. مسیر رابطه‌ها و کلیدهای اصلی/خارجی را تأیید کنید.
3. اگر نام ستون‌ها سازمانی یا مبهم است، در semantic layer معنی آن‌ها را ثبت کنید.
4. برای مقادیر فارسی، value mapping اضافه کنید؛ مانند «پست» ← `requester_role`.
5. برای جدول‌های حساس، ستون‌های غیرضروری را از catalog مجاز حذف کنید.
6. پس از هر تغییر ساختار یا معنی، lifecycle semantic را اجرا کنید:

```text
/semantic/lifecycle/run
```

7. freshness را بررسی کنید و فقط پس از `up_to_date` بودن پاسخ‌گویی را شروع کنید.

در UI ادمین ترتیب دکمه‌ها باید این باشد:

```text
خواندن اطلاعات دیتابیس
→ بررسی/اصلاح معنی جدول و ستون
→ ثبت اصلاح معنی
→ بررسی سلامت دیتابیس
→ به‌روزرسانی کامل سیستم
→ بررسی وضعیت semantic
```

اگر فقط داده‌های ردیف‌ها تغییر کرده‌اند و ساختار جدول ثابت است، به‌روزرسانی افزایشی کافی است. اگر جدول، ستون، foreign key یا معنی جدید اضافه شده، به‌روزرسانی کامل اجرا شود.

## ۴) اتصال گروه‌ها، گزارش‌ها و دانش سازمانی واقعی

### گروه‌ها

گروه‌ها مشخص می‌کنند سؤال به کدام حوزه مربوط است؛ مانند کارمند، دانش‌آموز، حقوق یا مدرسه. برای هر گروه، جدول‌های مجاز، ستون‌ها، joinها و مثال سؤال‌ها را ثبت کنید.

### گزارش‌ها

گزارش‌ها باید تعریف دقیق KPI، فیلترهای اجباری، ستون‌های خروجی و محدودیت دسترسی داشته باشند. گزارش را به جدول واقعی و query contract متصل کنید؛ از متن آزاد بدون منبع استفاده نکنید.

فایل‌های tenant در این مسیر نگهداری می‌شوند:

```text
knowledge/tenants/<TENANT_ID>/groups/
knowledge/tenants/<TENANT_ID>/reports/
```

`TENANT_ID` در `.env` باید دقیقاً با نام پوشه tenant برابر باشد. در Docker پوشه `knowledge` به کانتینر mount شده تا اصلاحات semantic بعد از restart از بین نروند.

پس از ایجاد یا ویرایش گروه/گزارش، sync گروه‌ها و گزارش‌ها را اجرا و سپس Retrieval Benchmark را بررسی کنید.

## ۵) انتخاب Provider مدل

### انتخاب مدل Ollama بر اساس RAM

| RAM سیستم | مدل پیشنهادی | کاربرد |
|---|---|---|
| ۸GB | `qwen2.5:3b` | دمو، تست و درخواست‌های سبک |
| ۱۶GB یا بیشتر | `qwen2.5:7b` | دقت بهتر و استفاده عادی |
| کمتر از ۸GB | OpenAI یا `LLM_ENABLED=false` | جلوگیری از فشار حافظه |

مدل 7B همراه با Windows، Docker، PostgreSQL، ChromaDB و API ممکن است روی سیستم ۸GB باعث کندی شدید یا استفاده زیاد از Page File شود. برای چنین سیستمی مدل 3B انتخاب مناسب‌تری است.

دانلود مدل 3B:

```bash
ollama pull qwen2.5:3b
```

دانلود مدل 7B:

```bash
ollama pull qwen2.5:7b
```

مدل‌های نصب‌شده را ببینید:

```bash
ollama list
```

برای تغییر مدل، مقدار زیر را در `.env` عوض کنید:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:3b
```

سپس کانتینر API را با تنظیمات جدید دوباره ایجاد کنید:

```bash
docker compose up -d --force-recreate api
```

برای اطمینان از اعمال تنظیم، لاگ و health را بررسی کنید:

```bash
docker compose logs --tail 100 api
curl http://localhost:8080/health
```

برای Ollama محلی:

```env
LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal
OLLAMA_MODEL=qwen2.5:7b
OPENAI_API_KEY=
```

برای OpenAI:

```env
LLM_ENABLED=true
LLM_PROVIDER=openai
OPENAI_API_KEY=کلید_واقعی
OPENAI_MODEL=gpt-4o-mini
```

داده حساس طبق Model Routing باید به provider محلی هدایت شود. کلید API را هرگز در فایل commit‌شده یا تصویر Docker قرار ندهید.

## ۶) عیب‌یابی و عملیات روزانه

```bash
docker compose ps
docker compose logs -f api
docker compose restart api
docker stats --no-stream
```

پس از تغییر کد Python، image را دوباره بسازید:

```bash
docker compose up -d --build api
```

پس از تغییر فقط `.env`، ایجاد مجدد کانتینر کافی است:

```bash
docker compose up -d --force-recreate api
```

### Semantic layer

برای هر مفهوم این موارد را ثبت کنید:

- نام فارسی و مترادف‌ها
- جدول و ستون واقعی
- نوع داده
- مقدارهای معتبر و mapping فارسی
- مسیر join
- تعریف aggregate و واحد اندازه‌گیری
- سطح دسترسی و حساسیت

پس از ثبت معنی، ترتیب عملیاتی این است:

```text
خواندن ساختار دیتابیس
→ ثبت اصلاح معنی
→ بررسی سلامت دیتابیس
→ به‌روزرسانی کامل/افزایشی سیستم
→ بررسی semantic freshness
→ اجرای Regression و Retrieval Benchmark
```

## ۷) چک‌لیست قبل از تحویل به کارفرما

- [ ] API و dependencyها داخل Docker اجرا می‌شوند.
- [ ] PostgreSQL واقعی با حساب read-only متصل است.
- [ ] Ollama یا provider انتخابی سالم است.
- [ ] جدول‌ها و join pathها تأیید شده‌اند.
- [ ] semantic layer وضعیت `up_to_date` دارد.
- [ ] پرسش‌های نمونه هر حوزه پاسخ درست می‌دهند.
- [ ] SQL فقط خواندنی و محدود به schema مجاز است.
- [ ] Token، latency، خطا و هزینه ثبت می‌شوند.
- [ ] backup و روش restore مستند شده است.
- [ ] `.env` و داده محرمانه در GitHub قرار نگرفته‌اند.
- [ ] مسیر مدل embedding روی سیستم مقصد موجود و داخل کانتینر mount شده است.
- [ ] `TENANT_ID` با پوشه دانش سازمانی برابر است.
- [ ] تست اتصال از داخل کانتینر API موفق است.
- [ ] پورت‌های 8080، 5433، 8001 و 11434 تداخل ندارند.
