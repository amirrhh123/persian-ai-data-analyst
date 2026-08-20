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

3. مقادیر `.env` را برای محیط مقصد تنظیم کنید؛ رمزها را در Git commit نکنید.

4. سرویس‌ها را build و اجرا کنید:

```bash
docker compose up -d --build
```

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
docker compose exec api python -c "from sqlalchemy import create_engine; print(create_engine('$DATABASE_URL').connect())"
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

## ۴) اتصال گروه‌ها، گزارش‌ها و دانش سازمانی واقعی

### گروه‌ها

گروه‌ها مشخص می‌کنند سؤال به کدام حوزه مربوط است؛ مانند کارمند، دانش‌آموز، حقوق یا مدرسه. برای هر گروه، جدول‌های مجاز، ستون‌ها، joinها و مثال سؤال‌ها را ثبت کنید.

### گزارش‌ها

گزارش‌ها باید تعریف دقیق KPI، فیلترهای اجباری، ستون‌های خروجی و محدودیت دسترسی داشته باشند. گزارش را به جدول واقعی و query contract متصل کنید؛ از متن آزاد بدون منبع استفاده نکنید.

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

## ۵) چک‌لیست قبل از تحویل به کارفرما

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

