# راهنمای تست و کار با سیستم Persian AI Data Analyst

این فایل برای مرحله ۱۱ است: یک راهنمای عملیاتی ساده برای اینکه بدانیم سیستم چطور کار می‌کند، چطور تست بگیریم، و اگر دیتابیس تغییر کرد یا جدول جدید اضافه شد چه کاری باید انجام شود.

## 1. سیستم دقیقاً چه کار می‌کند؟

کاربر یک سؤال فارسی می‌پرسد؛ سیستم آن را به SQL امن تبدیل می‌کند، روی PostgreSQL اجرا می‌کند و نتیجه را در UI نمایش می‌دهد.

جریان کلی:

```text
سؤال فارسی
  -> تشخیص موضوع و موجودیت: دانش‌آموز، کارمند، مدرسه، حقوق، بازنشستگی و ...
  -> استفاده از semantic layer برای فهم معنی ستون‌ها و رابطه جدول‌ها
  -> ساخت SQL فقط خواندنی
  -> اجرای SQL روی PostgreSQL
  -> نمایش پاسخ، جدول، SQL و trace در UI
```

## 2. اجزای اصلی

| بخش | نقش |
| --- | --- |
| FastAPI | API و داشبورد سیستم |
| PostgreSQL | دیتابیس اصلی سازمان |
| ChromaDB | ذخیره embedding گزارش‌ها و گروه‌ها برای جستجوی معنایی |
| Ollama | مدل زبانی محلی برای فهم زبان فارسی و کمک به تولید SQL |
| semantic layer | نقشه معنایی دیتابیس: جدول‌ها، ستون‌ها، aliasها، قوانین و joinها |
| benchmark | تست‌های کیفیت برای اینکه بعد از آپدیت مطمئن شویم سیستم خراب نشده |

## 3. semantic layer چیست؟

semantic layer یک فایل دانشی است که به سیستم می‌گوید:

- جدول `students` یعنی دانش‌آموزان
- ستون `national_id` یعنی کد ملی
- «سنوات» در سؤال کاربر یعنی ستون `pension_amount`
- برای فیلتر استان دانش‌آموز باید مسیر `students -> schools -> organization_units` استفاده شود
- برای سؤال «تعداد»، باید `COUNT` استفاده شود

فایل فعال فعلی اینجاست:

```text
schema/tenants/education_ministry/semantic_active.json
```

## 4. وقتی دیتابیس تغییر می‌کند چه اتفاقی می‌افتد؟

سیستم از دیتابیس fingerprint می‌گیرد. fingerprint یعنی یک شناسه از ساختار و نمونه داده‌ها.

اگر جدول، ستون، رابطه یا نمونه مقادیر مهم تغییر کند، fingerprint جدید با fingerprint ذخیره‌شده فرق می‌کند. در این حالت semantic layer قدیمی حساب می‌شود و باید آپدیت شود.

## 5. دستورهای اصلی اجرای سیستم

### 5.1 اجرای سرویس‌های دیتابیس و ChromaDB

```powershell
docker compose up -d
```

نکته: PostgreSQL روی پورت `5433` است و ChromaDB روی `8001`.

### 5.2 اجرای API

طبق تنظیم پروژه، بهتر است با Python 3.12 اجرا شود:

```powershell
python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8080
```

اگر خطای port already allocated گرفتی، یعنی یک سرور دیگر روی 8080 باز است. یا همان را استفاده کن، یا process قبلی را ببند.

### 5.3 باز کردن UI

در مرورگر:

```text
http://localhost:8080/dashboard
```

## 6. تست سریع سلامت سیستم

### 6.1 تست API

```powershell
Invoke-RestMethod http://localhost:8080/health
```

خروجی خوب:

```text
status: ok
ollama_connected: true
```

اگر `ollama_connected` false بود، باید Ollama و مدل را اجرا/بررسی کنی.

### 6.2 تست freshness semantic

```powershell
python scripts\check_semantic_freshness.py
```

خروجی خوب:

```text
status: up_to_date
```

یعنی semantic layer با دیتابیس فعلی هماهنگ است.

### 6.3 تست auto-update

```powershell
python scripts\auto_update_semantic_layer.py
```

اگر دیتابیس تغییر نکرده باشد:

```text
status: skipped
action: none
```

اگر دیتابیس تغییر کرده باشد:

```text
status: updated
action: lifecycle_run
```

## 7. تست از داخل UI

در داشبورد دکمه «بررسی و آپدیت خودکار» را بزن.

رفتار درست:

- اگر دیتابیس تغییر نکرده باشد، پیام می‌دهد نیازی به آپدیت نیست.
- اگر دیتابیس تغییر کرده باشد، خودش lifecycle کامل را اجرا می‌کند.
- بعد از پایان، benchmark باید پاس شود.

## 8. تست سؤال‌های فارسی

چند سؤال خوب برای تست:

```text
تعداد دانش‌آموزان فعال استان تهران چقدر است؟
```

```text
اطلاعات دانش آموز با کد ملی 3489881390
```

```text
سنوات کارمند با کد ملی 2475429291
```

```text
تعداد دانش آموزان مدرسه دبیرستان نمونه دولتی اصفهان
```

```text
کد ملی کارمند نسرین هاشمی با شغل کارمند اداری
```

```text
اسم مدارس استان تهران
```

برای خروجی‌های طولانی، UI باید جدول کامل را نشان دهد و فقط به چند ردیف اول محدود نشود.

## 9. تست اضافه شدن جدول جدید

برای اینکه دیتابیس اصلی خراب نشود، یک جدول demo امن داریم.

### 9.1 قبل از اضافه کردن جدول، وضعیت را چک کن

```powershell
python scripts\check_semantic_freshness.py
```

انتظار:

```text
status: up_to_date
```

### 9.2 جدول تستی را اضافه کن

```powershell
python scripts\simulate_schema_change.py add
```

این جدول ساخته می‌شود:

```text
demo_training_requests
```

### 9.3 دوباره freshness را چک کن

```powershell
python scripts\check_semantic_freshness.py
```

انتظار:

```text
status: stale
```

یعنی سیستم فهمیده دیتابیس عوض شده است.

### 9.4 آپدیت خودکار را اجرا کن

```powershell
python scripts\auto_update_semantic_layer.py --benchmark-limit 1
```

برای تست سریع `--benchmark-limit 1` کافی است. برای تست کامل، این گزینه را حذف کن:

```powershell
python scripts\auto_update_semantic_layer.py
```

انتظار بعد از آپدیت موفق:

```text
status: updated
freshness_after: up_to_date
```

### 9.5 جدول تستی را حذف کن

```powershell
python scripts\simulate_schema_change.py drop
```

بعد از حذف هم دیتابیس دوباره تغییر کرده، پس دوباره باید auto-update اجرا شود:

```powershell
python scripts\auto_update_semantic_layer.py --benchmark-limit 1
```

## 10. تست کامل کیفیت

برای اجرای benchmark کامل semantic:

```powershell
python scripts\run_semantic_benchmark.py --min-pass-rate 95
```

خروجی خوب:

```text
gate_status: passed
```

## 11. اجرای lifecycle کامل به صورت دستی

اگر خواستی بدون auto-update و مستقیم همه چیز rebuild شود:

```powershell
python scripts\run_semantic_lifecycle.py --min-pass-rate 95
```

این کار همیشه discovery، suggestions، activation و benchmark را اجرا می‌کند.

## 12. rollback اگر چیزی خراب شد

لیست نسخه‌های قبلی:

```powershell
python scripts\rollback_semantic_layer.py --list
```

برگشت به نسخه خاص:

```powershell
python scripts\rollback_semantic_layer.py --version-id VERSION_ID
```

## 13. APIهای مهم

| Endpoint | کاربرد |
| --- | --- |
| `GET /health` | سلامت API و Ollama |
| `GET /semantic/freshness` | بررسی هماهنگی semantic با دیتابیس |
| `POST /semantic/auto-update` | آپدیت خودکار فقط در صورت نیاز |
| `POST /semantic/lifecycle/run` | اجرای کامل lifecycle |
| `GET /semantic/versions` | لیست نسخه‌های قبلی semantic |
| `POST /semantic/rollback/{version_id}` | برگشت به نسخه قبلی |
| `POST /query` | اجرای سؤال فارسی |

## 14. خطاهای رایج

### port 8080 already allocated

یعنی API قبلاً اجرا شده است. همان پنجره قبلی را پیدا کن یا process قبلی را ببند.

### port 8000 / 8001 already allocated

یعنی ChromaDB یا سرویس دیگری روی آن پورت است. در این پروژه ChromaDB روی `8001` تنظیم شده است.

### ollama_connected false

یعنی Ollama اجرا نیست یا مدل آماده نیست. باید Ollama روشن باشد و مدل `qwen2.5:7b` موجود باشد.

### semantic freshness = stale

این خطا نیست؛ یعنی دیتابیس تغییر کرده. دکمه «بررسی و آپدیت خودکار» را بزن یا این دستور را اجرا کن:

```powershell
python scripts\auto_update_semantic_layer.py
```

## 15. مسیر پیشنهادی برای دمو به کارفرما

1. داشبورد را باز کن.
2. health را نشان بده.
3. یک سؤال ساده تعداد بپرس.
4. یک سؤال اطلاعات شخص با کد ملی بپرس.
5. SQL تولید شده را باز کن و نشان بده سیستم قابل ردیابی است.
6. دکمه «بررسی و آپدیت خودکار» را بزن.
7. اگر خواستی قسمت جذاب‌تر را نشان بدهی:
   - با `simulate_schema_change.py add` جدول demo اضافه کن.
   - نشان بده freshness می‌شود `stale`.
   - دکمه auto-update را بزن.
   - نشان بده سیستم خودش دوباره `up_to_date` می‌شود.

این مسیر برای ارائه خیلی خوب است چون نشان می‌دهد سیستم فقط جواب نمی‌دهد؛ خودش تغییر دیتابیس را هم تشخیص می‌دهد و امن آپدیت می‌شود.
