# Bazar Pulse: project plan

A self-running system that forecasts Dhaka's retail prices of essential goods
(rice, onion, eggs, oil, lentils…) from TCB's official daily price sheets. It
checks its own predictions against the real prices every day and retrains itself
only when a new model is actually better.

**The point of the project is the MLOps, not the model.** The forecast can be
simple. What makes it strong is that it runs, validates, monitors, retrains and
alerts by itself.

---

## 1. Facts about the data (checked on TCB's site, 2026-10-04 to 06)

| Fact | Detail |
|---|---|
| Source page | `https://tcb.gov.bd/pages/daily-rmps` ("ঢাকা মহানগরীর নিত্য প্রয়োজনীয় পণ্যের দৈনিক খুচরা বাজার দর") |
| Format | One **Excel (.xlsx)** file per day, published around 12:30 Bangladesh time |
| History | **~1,406 files, from May 2021 to today**, about 5 years |
| Listing | 10 files per page, `?page=1` … `?page=141` (page 1 = newest) |
| File host | Files live on a separate storage host: `objectstorage.ap-dcc-gazipur-1.oraclecloud15.com` |
| TLS | `tcb.gov.bd` fails certificate verification (same issue GSNA handled) |
| Rows per file | ~80 product rows (product × unit), e.g. "চাল সরু (নাজির/মিনিকেট), প্রতি কেজি" |
| Columns | Today's **min and max** price, plus min/max **1 week**, **1 month** and **1 year** ago, and % changes |

**Format drift seen between a 2021 and a 2026 file.** The parser must handle all of it:
- The sheet name changed: `Daily Report` became `Daily retail price`.
- The header row moved (row 6 vs row 5), and the date moved from a date cell to a text line ("তারিখঃ ০৪-১০-২০২৬").
- Product names changed: "চাল (মাঝারী)পাইজাম/**লতা**" became "পাইজাম/**আটাশ**". New products appear over time.
- Group-heading rows ("আটা/ময়দা", "ভোজ্য তেল") sit between data rows.
- `#DIV/0!` cells appear, and digits are mixed ("৫ লিটার" next to "2 লিটার").
- Some list entries have an empty date, and titles vary slightly.

---

## 2. What the system does

```
                    ┌──────────── every day, 14:00 BD time (GitHub Actions) ────────────┐
TCB daily Excel ──▶ │ 1. Fetch   → 2. Parse → 3. Validate → 4. Store                    │
                    │                              │ fail? stop, alert, keep last good   │
                    │ 5. Score yesterday's forecasts against today's real prices        │
                    │ 6. Predict the next 7 days with the CHAMPION model                │
                    │ 7. Publish: forecasts + metrics → commit → dashboard / API update │
                    └────────────────────────────────────────────────────────────────────┘

                    ┌──────────── every week (GitHub Actions) ───────────────────────────┐
                    │ Train CHALLENGER → backtest on the last 8 weeks                    │
                    │ Better than champion AND naive baseline? → promote (MLflow)       │
                    │ Otherwise keep the champion and log why                           │
                    └────────────────────────────────────────────────────────────────────┘

Rollback rule: if live error over 14 days is >1.3× the backtest error, revert to the
previous champion and send an alert.
```

**Prediction target:** the midpoint of today's price range, `(min + max) / 2`, for
each product, 1–7 days ahead.

---

## 3. Tools (all free)

| Job | Tool | Resume skill it proves |
|---|---|---|
| Scheduling | GitHub Actions (cron) | CI/CD, automation |
| Data storage | Parquet files committed to the repo, queried with DuckDB (SQL) | Data engineering, SQL, data versioning via git |
| Data validation | Pandera | Data contracts |
| Forecasting | statsforecast (baselines) + mlforecast with LightGBM | Time-series ML |
| Experiment tracking + model registry | MLflow (local, or free DagsHub server) for runs; champion/previous registry kept in git | Model registry |
| API | FastAPI in Docker, on Render's free plan | Docker, model serving |
| Dashboard | Streamlit Cloud | Deployment |
| Drift reports | PSI per category on fixed bins of 7-day price changes (custom; quantile-based tools collapse on prices that rarely move) | Monitoring |
| Alerts | Telegram bot | Alerting |
| *(Optional)* Kubernetes | Manifests tested on a local `kind` cluster | Kubernetes |

Why keep data in git: the files are small (~80 rows/day; 5 years ≈ 2 MB of Parquet,
raw Excel ≈ 40 MB, growing ~8 MB/year). Every daily update becomes a commit, so the
history *is* the data version log. No database server needed.

Side benefit: the daily data commit keeps the repo active, so GitHub never pauses
the scheduled workflows (it pauses them after 60 days without commits).

---

## 4. Repository layout

```
TCB/
├── src/bazarpulse/
│   ├── fetch.py        # polite downloader (rules adapted from GSNA)
│   ├── ingest.py       # walks the archive, downloads new files, keeps a manifest
│   ├── listing.py      # walks ?page=N, returns (date, xlsx_url) for every entry
│   ├── parse.py        # one Excel file → rows; finds columns by HEADER TEXT, not position
│   ├── catalog.py      # raw Bengali product names → stable product_id
│   ├── validate.py     # Pandera schema + cross-file checks
│   ├── features.py     # lags, momentum, category moves, same-week-last-year, calendar
│   ├── hijri.py        # Ramadan / Eid dates from the Hijri calendar
│   ├── train.py        # backtest, log to MLflow, register champion/challenger
│   ├── predict.py      # daily batch forecast with the champion
│   ├── monitor.py      # score yesterday, drift report, rollback rule
│   └── alerts.py       # Telegram messages
├── catalog/products.csv     # every raw name/unit seen → product_id, category, unit
├── data/
│   ├── raw/                 # original .xlsx files (immutable, one per day)
│   ├── clean/prices.parquet
│   ├── forecasts/           # one Parquet per run date
│   └── monitoring/metrics.parquet
├── api/                     # FastAPI app + Dockerfile
├── dashboard/streamlit_app.py
├── tests/fixtures/          # real files from 2021, 2024, 2026 to catch format drift
├── .github/workflows/
│   ├── ci.yml               # on every push/PR: lint, tests, data-contract tests
│   ├── daily.yml            # fetch → validate → predict → commit
│   └── retrain.yml          # weekly challenger vs champion
├── requirements.txt
└── README.md
```

---

## 5. Build phases

Each phase ends with a **"done when"** check. Don't start the next phase until it passes.

### Phase 0: Setup (1 day)

1. Create a **public** GitHub repo (public = free GitHub Actions minutes) and clone it into `E:\project\TCB`.
2. Create a virtual environment and the folder layout above.
3. Copy GSNA's `tools/polite.py` and `tools/fetch_cache.py` into `src/tcb/fetch.py`. Then:
   - **Change the User-Agent contact email to your own.** GSNA's has someone else's address.
   - Raise the per-host request budget for the one-time backfill (GSNA allows 25 per run), but **keep the ≥6 s delay**.
4. Add `.gitignore` (venv, `.env`, caches) and `.env.example`.

**Done when:** `python -c "import tcb"` works and the first commit is pushed.

### Phase 1: Data pipeline (week 1)

1. **Listing.** `listing.py` walks `?page=1..N` and collects `(publish_date, xlsx_url)`. It stops when a page has no rows. Store the result in `data/listing.csv`.
2. **Backfill download.** Fetch every file politely. ~1,550 requests at ≥6 s each ≈ **2.5–3 hours, once**. It's resumable because files are cached, so stopping and restarting is safe.
3. **Parser.** For each file:
   - Find the sheet by content, not by name.
   - Find the header row by the text "পণ্যের নাম".
   - Read the report date from the header lines (handle both the 2021 and 2026 styles).
   - Skip group-heading rows. Treat `#DIV/0!` and blanks as missing.
   - Convert Bengali digits to ASCII.
   - Output: `date, product_raw, unit_raw, price_min, price_max`.
4. **Catalog.** Collect every distinct `(product_raw, unit_raw)` from all files. Map each one to a stable `product_id` in `catalog/products.csv`, grouping old and new names (e.g. "পাইজাম/লতা" and "পাইজাম/আটাশ" → `rice_medium`).
   - Unknown names never disappear silently. They go to a review list, and validation warns about them.
5. **Validation (Pandera + custom checks):**
   - `price_min <= price_max`, prices > 0, within sane limits.
   - No duplicate `(product_id, date)`; dates not in the future; at least ~60 products per day.
   - **Cross-file check:** the "1 week ago" price in today's file should match the price stored 7 days ago. A mismatch means TCB revised a number or a parsing bug. Log it.
6. Write `data/clean/prices.parquet`.
7. **Tests.** Save three real files (2021, 2024, 2026) in `tests/fixtures/` and test the parser on each.

**Done when:**
- ≥95% of files parse.
- `prices.parquet` covers May 2021 to today.
- Tests pass on all three fixture years.
- You have a written list of the files that failed, and why.

### Phase 2: Explore and model (week 2)

1. **Explore (notebook):** plot price histories for ~10 key items. Look at gaps (Fridays, holidays) and at the **Ramadan/Eid effect** (onion, sugar, beef, dates). The Excel header even contains the Hijri date.
2. **Baselines** (statsforecast): Naive (tomorrow = today), SeasonalNaive (same weekday last week), moving average.
3. **Main model** (mlforecast + LightGBM): one global model across all products. Features:
   - Price history: lags 1/7/14/28 and rolling means.
   - Product category and day of week.
   - Days until Ramadan and Eid (use a Hijri-calendar package such as `hijridate`).
4. **Backtest:** rolling-origin cross-validation over the last ~6 months. Metrics per product: MAE, sMAPE, and **"% of products where the model beats Naive"**.
5. Log every run to **MLflow on DagsHub**. Register the best model and give it the `champion` alias.

**Done when:** you have a backtest table of model vs Naive per product, and a registered champion model. Write down honestly where Naive still wins.

### Phase 3: Daily automation and serving (week 3)

1. `daily.yml` runs at **08:00 UTC = 14:00 Bangladesh time**, with a retry at 11:00 UTC:
   1. Fetch today's file.
   2. Parse and validate it. **On failure: stop, alert, and keep yesterday's forecast.**
   3. Append to `prices.parquet`.
   4. Predict the next 7 days with the champion.
   5. Commit the data and forecasts.
2. **API:** FastAPI endpoints `/products`, `/forecast/{product_id}` and `/health`, packaged in a Dockerfile and deployed to Render.
3. **Dashboard** (Streamlit Cloud):
   - Pick a product to see its history and the 7-day forecast.
   - A "biggest expected rises this week" list.
   - "Source: TCB" with the date of the latest data.
   - A "not official, for information only" note.

**Done when:** the pipeline has run **3 days in a row without you touching it**, and the dashboard and API links work.

### Phase 4: Monitoring and retraining (week 4)

1. **Live scoring:** each day, compare yesterday's forecasts with today's real prices and append the result to `data/monitoring/metrics.parquet`. Add a "Model health" chart to the dashboard.
2. **Drift:** PSI per category comparing recent 7-day price changes with the year before (fixed bins), saved to `data/monitoring/drift.json`; alert when the set of drifted categories changes.
3. **Alerts** (Telegram), sent when:
   - The pipeline fails or validation fails.
   - Unknown products appear.
   - Live error stays above the threshold for 3 days.
   - Optionally, a "big rise expected" message for subscribers.
4. **Weekly retrain** (`retrain.yml`): train a challenger, backtest it on the last 8 weeks, and promote it only if it beats the champion by ≥2% MAE **and** beats Naive. Log the decision either way.
5. **Rollback rule** (see section 2), with an alert.
6. **CI** (`ci.yml`): on every push and PR, run lint (ruff), unit tests, parser tests on the fixtures, and a small training smoke test. When `main` changes, build the Docker image, push it to GHCR and trigger Render's deploy hook.

**Done when:** you can show a chart of live error over time, at least one logged retrain decision, and a test alert arriving on your phone.

### Phase 5: Polish (optional, week 5)

- A README with the architecture diagram, live links and honest results.
- A model card covering what it predicts, how good it is and its limits.
- Kubernetes manifests (Deployment + CronJob) tested on a local `kind` cluster.
- A short write-up or LinkedIn post: "What 5 years of TCB price data says about Ramadan price rises."

---

## 6. Risks and how the plan handles them

| Risk | Handling |
|---|---|
| TCB changes the Excel format | Header-by-text parsing + fixture tests; validation stops the pipeline and alerts instead of publishing garbage |
| TCB site down or broken certificate | Retry later in the day; per-host TLS probe from GSNA; yesterday's forecast stays up |
| Products renamed or added | Catalog mapping + review list; never silently dropped |
| Missing days (Fridays, holidays) | Model on publish days only; never invent prices to fill gaps |
| Naive baseline is hard to beat (prices often flat for weeks) | Report "beats Naive on X of N products" honestly; focus the story on the system |
| Overloading a government server | ≥6 s between requests, caching, one-time backfill, then 1–2 requests per day |
| Misleading users | "Source: TCB" + date on every number; "not official, for information only" notice |

---

## 7. Resume bullets to aim for (replace X with real results)

- Built a self-running MLOps pipeline that ingests TCB's daily Dhaka retail price sheets (5 years, ~1,400 files), validates them against a data contract, and publishes 7-day forecasts for X essential goods via a Dockerised FastAPI service and a public dashboard.
- Implemented live monitoring by scoring every forecast against next-day ground truth, with weekly champion/challenger retraining (GitHub Actions + MLflow registry) and automatic rollback. The model beat the naive baseline on X of N products (X% lower MAE).
- Designed format-drift-tolerant parsing and data-quality gates that caught X malformed or revised source files and halted the pipeline with Telegram alerts instead of publishing bad forecasts.
