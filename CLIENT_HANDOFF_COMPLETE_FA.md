# راهنمای کامل تحویل و اجرای سامانه تحلیل‌گر داده فارسی

این راهنما برای سیستم کارفرما نوشته شده است و محل اجرای هر دستور را مشخص می‌کند.

## ۱. پیش‌نیازهای سیستم کارفرما

روی Windows نصب باشد:

- Docker Desktop
- Python 3.12
- Git
- Ollama
- مدل Ollama مورد استفاده، مانند `gemma3:12b`

پوشه‌های حجیم زیر باید جداگانه روی سیستم کارفرما قرار داشته باشند و از GitHub دریافت نمی‌شوند:

```text
models/paraphrase-multilingual-mpnet-base-v2/
docker_wheels/
```

## ۲. دریافت پروژه از GitHub

محل اجرا: PowerShell کارفرما

```powershell
cd "D:\Project\AI"
git clone https://github.com/amirrhh123/persian-ai-data-analyst.git
cd persian-ai-data-analyst
```

اگر پروژه قبلاً Clone شده است:

```powershell
cd "D:\Project\AI\persian-ai-data-analyst"
git pull origin main
```

## ۳. قرار دادن مدل و wheelها

محل قرار دادن فایل‌ها: داخل پوشه اصلی پروژه

```text
D:\Project\AI\persian-ai-data-analyst\models\paraphrase-multilingual-mpnet-base-v2\
D:\Project\AI\persian-ai-data-analyst\docker_wheels\
```

ساختار مدل باید حداقل شامل این فایل‌ها باشد:

```text
config.json
model.safetensors یا pytorch_model.bin
modules.json
tokenizer.json
sentencepiece.bpe.model
1_Pooling/config.json
```

## ۴. نصب و بررسی Ollama

محل اجرا: PowerShell

```powershell
ollama list
```

اگر مدل وجود ندارد:

```powershell
ollama pull gemma3:12b
```

بررسی سلامت Ollama:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## ۵. تنظیم فایل `.env`

محل فایل: ریشه پروژه، کنار `docker-compose.yml`

اگر `.env` وجود ندارد:

```powershell
Copy-Item .env.example .env
```

برای اجرای دیتابیس دمو داخل Docker:

```env
DATABASE_HOST=localhost
DATABASE_PORT=5433
DATABASE_NAME=persian_ai
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres

CHROMA_HOST=localhost
CHROMA_PORT=8001

LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_HOST=localhost
OLLAMA_PORT=11434
OLLAMA_MODEL=gemma3:12b

EMBEDDING_MODEL_PATH=models/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DEVICE=cpu

API_HOST=0.0.0.0
API_PORT=8090
TENANT_ID=education_ministry
```

پس از هر تغییر در `.env` باید API Restart شود.

## ۶. اجرای نسخه فعلی با دیتابیس دمو

محل اجرا: PowerShell، داخل ریشه پروژه

```powershell
docker compose up -d postgres chromadb
docker compose ps
```

سپس API را بیرون Docker اجرا کنید:

```powershell
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8090
```

محل اجرای دستور بالا باید باز بماند.

در PowerShell دوم، بررسی سلامت:

```powershell
Invoke-RestMethod http://localhost:8090/health
```

رابط کاربری:

```text
http://localhost:8090/dashboard
```

## ۷. انتقال دیتابیس فعلی با فایل `backup.sql`

فایل `backup.sql` را جداگانه به کارفرما منتقل کنید؛ آن را داخل GitHub قرار ندهید.

### ۷.۱. قرار دادن فایل

فایل را در ریشه پروژه کارفرما بگذارید:

```text
D:\Project\AI\persian-ai-data-analyst\backup.sql
```

### ۷.۲. اجرای PostgreSQL

محل اجرا: PowerShell، داخل ریشه پروژه

```powershell
docker compose up -d postgres
```

بررسی نام Container:

```powershell
docker compose ps
```

اگر نام Container `persian_ai_postgres` است، ادامه دهید.

### ۷.۳. پاک‌سازی دیتابیس دمو (فقط اگر دیتابیس خالی یا قابل جایگزینی است)

محل اجرا: PowerShell

```powershell
docker exec persian_ai_postgres psql -U postgres -c "DROP DATABASE IF EXISTS persian_ai;"
docker exec persian_ai_postgres psql -U postgres -c "CREATE DATABASE persian_ai;"
```

این مرحله داده قبلی دیتابیس دمو را حذف می‌کند. روی دیتابیس واقعی اجرا نشود.

### ۷.۴. انتقال و واردکردن فایل SQL

محل اجرا: PowerShell، داخل ریشه پروژه

```powershell
docker cp .\backup.sql persian_ai_postgres:/tmp/backup.sql
docker exec persian_ai_postgres psql -U postgres -d persian_ai -f /tmp/backup.sql
```

بررسی جدول‌ها:

```powershell
docker exec persian_ai_postgres psql -U postgres -d persian_ai -c "\dt"
```

اگر فایل SQL با نام کاربر یا دیتابیس دیگری ساخته شده است، مقدارهای `-U` و `-d` را مطابق همان تنظیمات تغییر دهید.

## ۸. معرفی دیتابیس دمو به سیستم

پس از Restore دیتابیس، API را اجرا کنید:

```powershell
docker compose up -d chromadb
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8090
```

در داشبورد ادمین، به‌ترتیب این دکمه‌ها را بزنید:

1. خواندن اطلاعات دیتابیس
2. بررسی سلامت دیتابیس
3. به‌روزرسانی کامل سیستم
4. بررسی وضعیت Semantic

سپس این سؤال‌ها را تست کنید:

```text
تعداد دانش‌آموزان با نام پوریا
اطلاعات دانش‌آموز با کد ملی "1034567890"
تعداد دانش‌آموزان استان تهران
اطلاعات حقوق کارمند با نام زهرا کریمی
```

## ۹. اتصال یک دیتابیس جدید PostgreSQL

در این حالت معمولاً PostgreSQL جدید را داخل Docker پروژه اجرا نکنید؛ فقط ChromaDB را اجرا کنید.

### ۹.۱. ساخت کاربر فقط‌خواندنی

این بخش را مدیر دیتابیس روی PostgreSQL واقعی اجرا می‌کند، نه داخل پوشه پروژه:

```sql
CREATE USER ai_analyst WITH PASSWORD 'StrongPassword';
GRANT CONNECT ON DATABASE real_database TO ai_analyst;
GRANT USAGE ON SCHEMA public TO ai_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_analyst;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO ai_analyst;
```

### ۹.۲. تنظیم اتصال

در `.env` پروژه:

```env
DATABASE_HOST=192.168.1.20
DATABASE_PORT=5432
DATABASE_NAME=real_database
DATABASE_USER=ai_analyst
DATABASE_PASSWORD=StrongPassword

CHROMA_HOST=localhost
CHROMA_PORT=8001
TENANT_ID=client_database
```

سپس سرویس‌ها:

```powershell
docker compose up -d chromadb
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8090
```

### ۹.۳. ساخت لایه معنایی خودکار

در پنل ادمین:

1. خواندن اطلاعات دیتابیس
2. بررسی سلامت دیتابیس
3. به‌روزرسانی کامل سیستم
4. بررسی وضعیت Semantic

سیستم جدول‌ها، ستون‌ها، نوع داده، کلیدها، روابط، نمونه مقادیر و معناهای اولیه را استخراج می‌کند. اگر اصطلاحی اشتباه بود، آن را در بخش اصلاح معنایی ثبت و سپس به‌روزرسانی کامل سیستم را اجرا کنید.

## ۱۰. اضافه‌کردن جدول جدید به دیتابیس متصل

ابتدا جدول را در PostgreSQL ایجاد یا وارد کنید. سپس در پنل:

1. خواندن اطلاعات دیتابیس
2. بررسی سلامت دیتابیس
3. به‌روزرسانی کامل سیستم
4. در صورت نیاز ثبت اصلاح معنای جدول یا ستون

برای تغییر داده‌های جدول‌های موجود، معمولاً فقط اجرای سؤال کافی است. برای تغییر ساختار جدول، Discovery و Semantic Lifecycle را دوباره اجرا کنید.

## ۱۱. SQL Server

نسخه فعلی به‌صورت کامل برای PostgreSQL آماده است. برای SQL Server باید Adapter اتصال، Schema Discovery و T-SQL Dialect اضافه شود. فقط تغییر `DATABASE_PORT` کافی نیست. تا قبل از اضافه‌شدن این Adapter، دیتابیس واقعی کارفرما باید PostgreSQL باشد.

## ۱۲. توقف و راه‌اندازی مجدد

توقف API: در پنجره‌ای که Uvicorn اجرا شده، `Ctrl+C`.

توقف سرویس‌های Docker، بدون حذف داده‌ها:

```powershell
docker compose stop
```

راه‌اندازی دوباره:

```powershell
docker compose up -d postgres chromadb
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8090
```

از اجرای `docker compose down -v` خودداری کنید؛ این دستور Volume دیتابیس را حذف می‌کند.

## ۱۳. به‌روزرسانی‌های بعدی پروژه

محل اجرا: PowerShell، داخل ریشه پروژه کارفرما

```powershell
git pull origin main
docker compose up -d postgres chromadb
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8090
```

فایل `.env` موجود را با `.env.example` مقایسه کنید و آن را بدون بررسی بازنویسی نکنید.

## ۱۴. خطاهای رایج

### پورت 8080 یا 8090 اشغال است

یک پورت آزاد انتخاب کنید:

```powershell
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8091
```

سپس از `http://localhost:8091/dashboard` استفاده کنید.

### API به PostgreSQL وصل نمی‌شود

مقادیر `DATABASE_HOST`، `DATABASE_PORT`، نام دیتابیس، کاربر و رمز را بررسی کنید. از داخل PowerShell تست کنید:

```powershell
Test-NetConnection DATABASE_HOST -Port DATABASE_PORT
```

### Ollama متصل نیست

```powershell
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

### پاسخ‌ها مربوط به ساختار قبلی هستند

API را Restart کنید و در پنل «خواندن اطلاعات دیتابیس» و سپس «به‌روزرسانی کامل سیستم» را اجرا کنید.

