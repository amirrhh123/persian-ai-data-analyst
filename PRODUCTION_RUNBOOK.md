# Production Runbook — Persian AI Data Analyst

این فایل راهنمای عملیاتی اجرای محصول روی دیتابیس واقعی است. هدف این است که تیم فنی یا اپراتور بتواند بدون دستکاری کد، سیستم را اجرا، بررسی، به‌روزرسانی، تست، rollback و عیب‌یابی کند.

## 1. اجرای سرویس‌ها

### 1.1 اجرای PostgreSQL و ChromaDB

```powershell
docker compose up -d
```

بررسی وضعیت:

```powershell
docker compose ps
```

نکته‌ها:

- PostgreSQL پروژه روی host port `5433` است.
- ChromaDB ممکن است روی port متفاوت از `8000` تنظیم شده باشد؛ اگر port اشغال بود، `docker-compose.yml` را بررسی کنید.

### 1.2 اجرای API

```powershell
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
```

اگر خطای port گرفتید:

```powershell
netstat -ano | findstr :8080
taskkill /PID <PID> /F
```

داشبورد:

```text
http://localhost:8080/dashboard
```

## 2. Health check سریع

```powershell
Invoke-RestMethod http://localhost:8080/health
```

خروجی قابل قبول:

```text
status: ok
ollama_connected: true
```

اگر `ollama_connected=false` بود، Ollama یا مدل محلی را بررسی کنید.

### 2.1 Lightweight mode / اجرای بدون Ollama

اگر می‌خواهید سیستم سبک‌تر اجرا شود و به Ollama وابسته نباشد، در فایل `.env` این مقدار را قرار دهید:

```env
LLM_ENABLED=false
```

بعد از تغییر `.env` حتماً API را یک بار خاموش و دوباره روشن کنید، چون تنظیمات برنامه در زمان شروع سرویس خوانده می‌شوند.

در این حالت، `/health` باید چیزی شبیه این نشان دهد:

```text
mode: lightweight
llm_enabled: false
llm_required: false
```

در حالت سبک:

- سؤال‌های دیتابیسی که توسط semantic layer، templateها و ruleها پوشش داده شده‌اند همچنان کار می‌کنند.
- PostgreSQL و ChromaDB همچنان برای دیتابیس، schema، semantic و جست‌وجوی ساختار لازم هستند.
- Ollama لازم نیست روشن باشد.
- مسیرهای مستقیم مدل زبانی مثل `/llm/chat` و `/llm/sql-test` عمداً `503` می‌دهند.
- اگر سؤال خیلی آزاد، توضیحی یا خارج از الگوهای semantic باشد، سیستم به جای حدس خطرناک، خطای قابل توضیح برمی‌گرداند.

برای برگشت به حالت کامل:

```env
LLM_ENABLED=true
```

سپس API را restart کنید و در `/health` مقدار `llm_enabled: true` را ببینید.

## 3. Onboarding دیتابیس جدید

ترتیب استاندارد برای دیتابیس جدید:

```text
database discovery
schema onboarding report
schema quality gate
semantic suggestions
human review
activation
smoke tests
benchmark
```

### 3.1 کشف schema

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/database/discovery/sync"
```

خروجی در این مسیر ذخیره می‌شود:

```text
schema/tenants/<tenant_id>/discovery.json
```

### 3.2 گزارش onboarding

```powershell
Invoke-RestMethod "http://localhost:8080/database/onboarding-report"
```

این گزارش نشان می‌دهد:

- تعداد جدول‌ها
- تعداد ستون‌ها
- روابط کشف‌شده
- ستون‌های حساس
- جدول‌های بدون primary key
- ستون‌های متنی بدون sample value
- جدول‌های بزرگ بدون index
- پیشنهادهای اصلاح

### 3.3 Schema quality gate

```powershell
Invoke-RestMethod "http://localhost:8080/database/schema-quality-gate"
```

وضعیت‌ها:

- `passed`: آماده ادامه کار
- `passed_with_warnings`: قابل ادامه، اما بهتر است هشدارها بررسی شوند
- `blocked`: semantic نباید فعال شود

## 4. ساخت و فعال‌سازی semantic layer

### 4.1 تولید semantic suggestions

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/suggestions/sync"
```

خروجی:

```text
schema/tenants/<tenant_id>/semantic_suggestions.json
```

### 4.2 Human review

برای تأیید جدول:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/review" `
  -ContentType "application/json" `
  -Body '{"target_type":"table","table":"training_requests","display_name_fa":"درخواست‌های آموزشی","aliases_fa":["درخواست آموزشی"],"entity":"training_request","approved":true}'
```

برای تأیید ستون:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/review" `
  -ContentType "application/json" `
  -Body '{"target_type":"column","table":"training_requests","column":"requester_role","display_name_fa":"پست درخواست‌دهنده","aliases_fa":["پست","سمت"],"value_type":"category","approved":true}'
```

### 4.3 اعتبارسنجی semantic

```powershell
Invoke-RestMethod "http://localhost:8080/semantic/validate"
```

### 4.4 فعال‌سازی semantic

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/activate"
```

فایل فعال:

```text
schema/tenants/<tenant_id>/semantic_active.json
```

## 5. چرخه خودکار update

برای اجرای کل lifecycle:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/auto-update?min_pass_rate=95"
```

این مسیر به‌ترتیب انجام می‌دهد:

```text
freshness check
schema discovery
schema quality gate
semantic suggestions
activation
benchmark
```

اگر دیتابیس تغییر نکرده باشد، status معمولاً `skipped` است.

## 6. Smoke-test و benchmark

### 6.1 ساخت smoke-test خودکار

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/smoke-tests/sync"
```

خروجی:

```text
tests/benchmark/generated_smoke_cases.json
```

### 6.2 اجرای smoke-test

بدون اجرای واقعی SQL:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/smoke-tests/run?limit=20"
```

با اجرای واقعی SQL:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/smoke-tests/run?limit=20&execute=true"
```

خروجی‌ها:

```text
tests/results/semantic_smoke_test_<timestamp>.json
tests/results/latest_semantic_smoke_test.json
```

### 6.3 Benchmark اصلی

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/benchmark/run?limit=10"
```

یا در تست‌های Python:

```powershell
python -m pytest tests/test_regression_benchmark.py -q
```

## 7. Rollback

لیست نسخه‌ها:

```powershell
Invoke-RestMethod "http://localhost:8080/semantic/versions"
```

Rollback:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/rollback/<version_id>"
```

هر activation قبلی backup می‌سازد تا بتوان به نسخه سالم قبلی برگشت.

## 8. Audit و observability

### 8.1 لاگ اجرای SQL

مسیر audit:

```text
logs/execution_audit.jsonl
```

در audit مقدارهای حساس redacted می‌شوند.

### 8.2 خلاصه audit

```powershell
Invoke-RestMethod "http://localhost:8080/sql/audit/summary"
```

نمایش می‌دهد:

- queryهای موفق
- queryهای رد شده
- خطاها
- میانگین زمان اجرا
- آخرین eventها

## 9. امنیت داده

مشاهده policy:

```powershell
Invoke-RestMethod "http://localhost:8080/security/data-policy"
```

ستون‌هایی مثل این‌ها mask می‌شوند:

- `national_id`
- `phone`
- `mobile`
- `email`
- `address`
- `salary`
- `iban`
- `card`
- `account`

مثال:

```text
8223876400 -> ***6400
```

## 10. Error taxonomy

مشاهده codeها:

```powershell
Invoke-RestMethod "http://localhost:8080/errors/taxonomy"
```

codeهای مهم:

- `ambiguity.related_filter`
- `safety.rejected`
- `unsupported.out_of_scope`
- `sql.validation_failed`
- `execution.failed`
- `routing.no_sql`
- `expectation.mismatch`

در smoke-testها فیلد `error_code` کمک می‌کند بفهمیم شکست از کدام لایه بوده است.

## 11. Runbook رفع خطاهای رایج

### 11.1 Port already allocated

نشانه:

```text
WinError 10048
```

راه‌حل:

```powershell
netstat -ano | findstr :8080
taskkill /PID <PID> /F
```

### 11.2 Docker port conflict

نشانه:

```text
Bind for 0.0.0.0:8000 failed: port is already allocated
```

راه‌حل:

- سرویس اشغال‌کننده port را ببندید، یا
- port مربوط به ChromaDB را در `docker-compose.yml` تغییر دهید.

### 11.3 Semantic stale

نشانه:

```text
status: stale
```

راه‌حل:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/semantic/auto-update?min_pass_rate=95"
```

### 11.4 Schema quality blocked

راه‌حل:

```powershell
Invoke-RestMethod "http://localhost:8080/database/schema-quality-gate"
```

سپس `recommended_actions` را انجام دهید.

### 11.5 Smoke-test failed

آخرین نتیجه را ببینید:

```text
tests/results/latest_semantic_smoke_test.json
```

به این فیلدها نگاه کنید:

- `failure_stage`
- `error_code`
- `sql`
- `failures`

### 11.6 خروجی اشتباه برای جدول جدید

ترتیب بررسی:

1. `/database/onboarding-report`
2. `/database/schema-quality-gate`
3. `/semantic/suggestions`
4. `/semantic/review`
5. `/semantic/activate`
6. `/semantic/smoke-tests/run`

## 12. چک‌لیست قبل از ارائه به کارفرما

- [ ] Docker services روشن هستند.
- [ ] API روی `8080` اجراست.
- [ ] `/health` سالم است.
- [ ] Dashboard باز می‌شود.
- [ ] `/database/schema-quality-gate` blocked نیست.
- [ ] `/semantic/smoke-tests/run?limit=20` pass rate قابل قبول دارد.
- [ ] `/sql/audit/summary` eventها را نشان می‌دهد.
- [ ] `/security/data-policy` ستون‌های حساس را نشان می‌دهد.
- [ ] rollback version وجود دارد.
- [ ] چند سؤال نمایشی از قبل آماده شده‌اند.

## 13. مسیر پیشنهادی برای دیتابیس واقعی کارفرما

1. اتصال read-only به PostgreSQL واقعی
2. اجرای discovery
3. بررسی onboarding report
4. رفع blockerهای schema
5. تولید semantic suggestions
6. review انسانی برای جدول‌ها/ستون‌های کم‌اعتماد
7. فعال‌سازی semantic
8. تولید و اجرای smoke-test
9. اجرای benchmark
10. ارائه demo از dashboard

## 14. معیار آماده بودن برای production

سیستم زمانی آماده production است که:

- schema quality gate برابر `passed` یا `passed_with_warnings` باشد.
- خطای `blocked` وجود نداشته باشد.
- semantic active با fingerprint فعلی دیتابیس هماهنگ باشد.
- smoke-testهای جدول‌های جدید pass rate قابل قبول داشته باشند.
- data policy فعال باشد.
- audit summary eventها را ثبت کند.
- rollback قابل انجام باشد.
