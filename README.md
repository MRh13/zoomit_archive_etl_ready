# ZenML Archive ETL — Page-Batch Architecture

پروژهٔ **ZenML Archive ETL** یک پایپ‌لاین ETL برای استخراج، deduplication و ذخیره‌سازی آرشیو مقالات وب‌سایت‌های خانوادهٔ Zoomit است. این پروژه با **ZenML** ارکستری می‌شود و هر صفحهٔ آرشیو را به‌عنوان یک batch مستقل پردازش می‌کند.

دامنه‌های پشتیبانی‌شده:

| دامنه   | آدرس پایه              |
|---------|------------------------|
| zoomit  | https://www.zoomit.ir  |
| kojaro  | https://www.kojaro.com |
| zoomg   | https://www.zoomg.ir   |
| pedal   | https://www.pedal.ir   |
| filmzi  | https://www.filmzi.com |
| zoomon  | https://www.zoomon.ir  |

---

## هدف پروژه

هدف اصلی این معماری:

1. **حذف الگوی «یک ZenML step برای هر مقاله»** — به‌جای ساختن صدها step، هر صفحهٔ آرشیو (حدود ۲۰ مقاله) یک step است.
2. **جدا کردن deduplication از ZenML cache** — کنترل «آیا این URL قبلاً ingest شده؟» در PostgreSQL انجام می‌شود، نه در cache ZenML.
3. **کنترل هزینهٔ مرورگر** — یک Selenium WebDriver برای کل صفحه (نه برای هر مقاله).
4. **خروجی Bronze مستقل** — هر page یک فایل Parquet جدا می‌نویسد تا اجرای موازی race condition نداشته باشد.

---

## معماری پایپ‌لاین

```text
initialize_database
        │
        ▼
   load_urls  ──────────────────────►  لیست URLهای صفحات آرشیو
        │                                 (یک artifact sequence)
        │
        ▼
process_archive_page  (برای هر page به‌صورت dynamic)
        │
        ├── discover anchors          (کشف لینک مقالات از صفحه)
        ├── PostgreSQL claim / dedup  (claim قبل از scrape)
        ├── یک Chrome برای کل page
        ├── scrape فقط مقالات جدید
        ├── validate + log
        ├── PostgreSQL upsert
        └── Parquet bronze shard
```

### چرا page به‌عنوان batch؟

اگر برای هر مقاله یک step ساخته شود:

- تعداد stepها به‌سرعت به هزاران عدد می‌رسد.
- overhead ZenML (artifact store، metadata، scheduling) غالب می‌شود.
- ساختن ۲۰ process کروم برای ۲۰ مقالهٔ یک صفحه بسیار پرهزینه است.

در این پروژه:

```text
1 archive page  =  1 ZenML step  =  ≤ 20 article candidates
```

و lifecycle مرورگر در سطح همان page کنترل می‌شود.

### نکتهٔ مهم دربارهٔ Windows و `step.map()`

روی Windows، artifact store محلی نمی‌تواند دایرکتوری‌هایی که کاراکتر `:` دارند بسازد. شناسه‌های mapped step در ZenML اغلب به شکل زیر هستند:

```text
map:process_archive_page:0
```

این باعث `WinError 123` می‌شود. بنابراین در نسخهٔ فعلی، پایپ‌لاین **dynamic** است ولی به‌جای `step.map()`، لیست صفحات را load می‌کند و برای هر صفحه یک فراخوانی عادی `process_archive_page` می‌سازد.

این کار مقیاس‌پذیری منطقی (page = batch) را حفظ می‌کند و فقط روی orchestrator محلی Windows به‌صورت sequential اجرا می‌شود. در production روی Linux / Kubernetes می‌توان parallelism مبتنی بر map را دوباره فعال کرد.

---

## Cache policy

| Step                    | Cache | دلیل                                      |
|-------------------------|-------|-------------------------------------------|
| `load_urls`             | روشن  | خروجی deterministic است                   |
| `initialize_database`   | خاموش | وضعیت schema به runtime وابسته است        |
| `process_archive_page`  | خاموش | محتوای وب خارجی و وضعیت DB قابل cache نیست |

**کنترل واقعی ingest در PostgreSQL انجام می‌شود**، نه در ZenML cache.

---

## PostgreSQL — deduplication و claim

دو جدول اصلی:

### `archive_articles`

منبع durable دادهٔ ingest‌شده.

- کلید اصلی: `url`
- unique index جزئی: `(domain, token)` (وقتی token موجود باشد)

فیلدهای اصلی شامل title، lead، content، tags، images، scraped_at و غیره هستند.

### `article_ingestion`

وضعیت claim هر URL:

| وضعیت   | معنی                                      |
|---------|-------------------------------------------|
| claimed | یک worker در حال scrape است               |
| done    | با موفقیت ingest شده                      |
| failed  | scrape شکست خورده؛ در run بعدی قابل retry |

رفتار claim:

1. قبل از scrape، claim گرفته می‌شود.
2. اگر مقاله قبلاً در `archive_articles` باشد → scrape انجام نمی‌شود.
3. اگر worker دیگری claim را گرفته باشد → این batch آن را skip می‌کند.
4. claimهای stale بعد از `CLAIM_STALE_AFTER_SECONDS` قابل reclaim هستند.
5. در صورت خطا، وضعیت به `failed` تغییر می‌کند و در اجرای بعدی retry می‌شود.

به این ترتیب **ZenML cache** و **data deduplication** کاملاً از هم جدا هستند.

---

## ذخیره‌سازی

### PostgreSQL

- دادهٔ canonical مقالات
- deduplication و وضعیت ingestion
- operational state

### Parquet (Bronze)

```text
data/bronze/archive_articles/
    domain=zoomit/
        run_date=YYYY-MM-DD/
            page_<fingerprint>.parquet
```

- fingerprint بر اساس URLهای همان batch ساخته می‌شود.
- هر page یک shard مستقل می‌نویسد → بدون race condition روی فایل مشترک.
- برای object storage می‌توان `PARQUET_ROOT` را به مسیر `s3://...` تغییر داد (`fsspec` و `s3fs` در dependencies هستند).

### Media (اختیاری)

تصاویر مقالات در مسیر `MEDIA_ROOT` ذخیره می‌شوند (قابل غیرفعال‌سازی با `DOWNLOAD_IMAGES=false`).

---

## Logging و metadata

تمام لاگرها از:

```python
from zenml.logger import get_logger
```

استفاده می‌کنند. لاگ‌ها در Dashboard ZenML قابل مشاهده‌اند.

**سطح مقاله:**

```text
status, domain, url, title, word_count, tag_count, duration_ms
```

**سطح page batch (به‌عنوان step metadata):**

```text
discovered, skipped_existing, claimed, scraped, persisted, failed, duration_ms, parquet_path
```

این metadata برای مقایسهٔ runها و مشاهدهٔ metricها مفید است.

---

## ساختار پروژه

```text
zenml_archive_etl_zoomon_ready/
├── run.py                      # نقطهٔ ورود CLI
├── pipelines/
│   └── archive_data_etl.py     # پایپ‌لاین dynamic
├── steps/
│   ├── initialize_database.py
│   ├── load_urls.py
│   └── process_archive_page.py
├── storage/
│   ├── config.py               # Settings از .env
│   ├── postgres.py             # schema + claim + upsert
│   ├── scraper.py              # استخراج محتوا
│   ├── browser.py              # Selenium lifecycle
│   ├── selectors.py            # CSS selectors مشترک
│   ├── identity.py             # استخراج domain/token
│   ├── parquet.py              # نوشتن Bronze
│   └── images.py               # دانلود تصاویر
├── scripts/
│   ├── init_db.py              # ایجاد schema
│   └── check_postgres.py       # تست اتصال
├── tests/
├── data/                       # bronze + media (runtime)
├── chromedriver/
├── docker-compose.yml          # PostgreSQL
├── requirements.txt
├── pyproject.toml
├── .env                        # تنظیمات محلی
└── README.md
```

---

## نصب و راه‌اندازی

### پیش‌نیازها

- Python ≥ 3.10
- Docker (برای PostgreSQL)
- Chrome / Chromium (برای Selenium)

### ۱. محیط مجازی

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### ۲. فایل محیط

فایل `.env` از قبل در ریشهٔ پروژه وجود دارد. مقادیر پیش‌فرض برای توسعهٔ محلی با docker-compose تنظیم شده‌اند:

```text
POSTGRES_DSN=postgresql://archive_user:archive_password@127.0.0.1:15432/archive
```

در صورت نیاز می‌توانید `PARQUET_ROOT`، `MEDIA_ROOT`، `MAX_ARTICLES_PER_PAGE` و سایر متغیرها را تغییر دهید.

### ۳. راه‌اندازی PostgreSQL

```bash
docker compose up -d postgres
```

بررسی وضعیت:

```bash
docker compose ps
```

انتظار:

```text
0.0.0.0:15432->5432/tcp   healthy
```

پورت میزبان عمداً `15432` است تا با PostgreSQL محلی روی `5432` تداخل نداشته باشد.

### ۴. ایجاد schema

```bash
python -m scripts.init_db
```

### ۵. تست اتصال

```bash
python -m scripts.check_postgres
```

یا:

```bash
python -c "import psycopg; conn=psycopg.connect(host='127.0.0.1', port=15432, dbname='archive', user='archive_user', password='archive_password'); print(conn.execute('SELECT current_user, current_database()').fetchone()); conn.close()"
```

خروجی مورد انتظار:

```text
('archive_user', 'archive')
```

---

## اجرای پایپ‌لاین

### تست کوچک (فقط صفحهٔ اول هر دامنه)

```bash
python run.py --first-page
```

### یک دامنه

```bash
python run.py --domain zoomit
python run.py --domain zoomon
python run.py --domain kojaro
```

دامنه‌های معتبر: `zoomit`, `kojaro`, `zoomg`, `pedal`, `filmzi`, `zoomon`

### کل آرشیو (همهٔ دامنه‌ها، صفحات ۱ تا ۵۰۰)

```bash
python run.py
```

### رفتار اجرای دوم

اگر run اول برای یک صفحه این را گزارش کند:

```text
20 discovered
20 scraped
20 persisted
```

run دوم انتظار می‌رود:

```text
20 discovered
20 skipped_existing
0 scraped
0 persisted
```

اگر ۳ مقالهٔ جدید اضافه شده باشد:

```text
20 discovered
17 skipped_existing
3 scraped
3 persisted
```

---

## متغیرهای محیطی (`.env`)

| متغیر                        | پیش‌فرض                                      | توضیح                                      |
|-----------------------------|----------------------------------------------|--------------------------------------------|
| `POSTGRES_USER`             | `archive_user`                               | کاربر PostgreSQL                           |
| `POSTGRES_PASSWORD`         | `archive_password`                           | رمز عبور                                   |
| `POSTGRES_DB`               | `archive`                                    | نام دیتابیس                                |
| `POSTGRES_HOST_PORT`        | `15432`                                      | پورت میزبان برای docker-compose            |
| `POSTGRES_DSN`              | `postgresql://...@127.0.0.1:15432/archive`   | DSN کامل برای psycopg                      |
| `PARQUET_ROOT`              | `data/bronze/archive_articles`               | مسیر Bronze (محلی یا s3://)                |
| `MEDIA_ROOT`                | `data/media`                                 | مسیر تصاویر                                |
| `MAX_ARTICLES_PER_PAGE`     | `20`                                         | سقف مقالات در هر page batch                |
| `CLAIM_STALE_AFTER_SECONDS` | `3600`                                       | زمان reclaim claimهای stale                |
| `REQUEST_TIMEOUT_SECONDS`   | `20`                                         | timeout درخواست‌ها                         |
| `DOWNLOAD_IMAGES`           | `true`                                       | دانلود تصاویر مقالات                       |
| `ZENML_LOGGING_VERBOSITY`   | `INFO`                                       | سطح لاگ ZenML                              |

---

## پاک‌سازی PostgreSQL

توقف بدون حذف داده:

```bash
docker compose down
```

حذف container + volume (تمام داده‌ها پاک می‌شود — **مخرب**):

```bash
docker compose down -v
```

راه‌اندازی تمیز از صفر:

```bash
docker compose down -v
docker compose up -d postgres
python -m scripts.init_db
```

---

## Troubleshooting

### بررسی container

```bash
docker compose ps
docker exec -it zenml_archive_postgres psql -U archive_user -d archive -c "SELECT current_user, current_database();"
```

### تست اتصال از پایتون

```bash
python -m scripts.check_postgres
```

### خطای مسیر روی Windows (`WinError 123`)

این پروژه عمداً از `step.map()` روی orchestrator محلی Windows استفاده نمی‌کند. اگر هنوز شناسه‌هایی شبیه `map:process_archive_page:0` می‌بینید، نسخهٔ پایپ‌لاین را بررسی کنید.

### Selenium / Chrome

اطمینان حاصل کنید Chrome نصب است و `chromedriver` در مسیر پروژه یا PATH قرار دارد.

---

## مسیر ارتقا (Upgrade path)

```text
Archive pages
      ↓
Page Batch (≤ 20 articles)
      ↓
Dedup / Claim (PostgreSQL)
      ↓
Scrape + Validation
      ↓
Parquet Bronze / Object Storage
      ↓
PostgreSQL (canonical)
      ↓
Warehouse / Analytics
      ↓
Monitoring / Metrics / Alerts
```

CSV عمداً از مسیر اصلی ingestion حذف شده است.

برای production پیشنهاد می‌شود:

- از ZenML server + orchestrator مناسب (local_docker / Kubernetes / remote) استفاده شود.
- `runtime="isolated"` برای اجرای موازی page batchها فعال شود.
- metricهای زیر در Dashboard و در صورت نیاز OpenTelemetry / Prometheus منتشر شوند:
  - pages discovered / completed / failed
  - articles discovered / skipped / scraped / persisted
  - scrape error count
  - average article & page latency
  - articles/sec
  - stale claims
  - PostgreSQL و Parquet write latency

---

## منابع

- [ZenML Dynamic Pipelines](https://docs.zenml.io/concepts/steps_and_pipelines/dynamic_pipelines)
- [ZenML Execution](https://docs.zenml.io/concepts/steps_and_pipelines/execution)
- [ZenML Logging](https://docs.zenml.io/concepts/steps_and_pipelines/logging)
- [ZenML Metadata](https://docs.zenml.io/concepts/metadata)
- [ZenML Advanced Caching](https://docs.zenml.io/concepts/steps_and_pipelines/advanced_features)
