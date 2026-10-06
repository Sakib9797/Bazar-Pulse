# 🛒 Bazar Pulse

**Self-running price forecasts for Dhaka's essential goods**, built from the official daily
retail price sheets of the Trading Corporation of Bangladesh (TCB).

Every day the system downloads TCB's new price sheet, validates it, checks yesterday's
forecasts against the real prices, and publishes a 7-day forecast for ~60 products (rice,
onion, eggs, oil, lentils, sugar…). Every week it trains challenger models and replaces the
champion **only if a challenger is measurably better**. If live accuracy degrades, it rolls
back to the previous model on its own.

> The point of this project is the MLOps: a pipeline that runs, validates, monitors,
> retrains and alerts without anyone touching it.

<!-- LIVE-LINKS -->

---

## Why this data

- **Real impact.** Onion, egg and oil price spikes are national news in Bangladesh.
- **Ground truth arrives every day.** Tomorrow's TCB sheet tells us whether today's forecast
  was right, so the system monitors **real** accuracy, not proxies.
- **Messy, real-world input.** Bengali Excel files whose layout drifted over 5 years
  (see [Data](#data)), which makes data validation and contracts essential.

## How it works

```
                 ┌──────── daily, 14:00 Bangladesh time (GitHub Actions) ────────┐
TCB daily Excel ─▶ fetch ─▶ parse ─▶ validate ─▶ store (Parquet in git)             │
                 │                      │ hard failure: stop, alert, keep last good │
                 │ score yesterday's forecasts vs today's real prices              │
                 │ health check (rollback if live error > 1.3× backtest) + drift    │
                 │ forecast next 7 days with the champion ─▶ commit ─▶ API/dashboard │
                 └───────────────────────────────────────────────────────────────────┘
                 ┌──────── weekly (GitHub Actions) ──────────────────────────────────┐
                 │ backtest every candidate on the last 8 weeks (MLflow-tracked)     │
                 │ switch champion only if ≥2% better AND better than "no change"    │
                 └───────────────────────────────────────────────────────────────────┘
```

| Stage | What it does | Code |
|---|---|---|
| Fetch | Walks TCB's paginated archive, downloads new Excel files politely (≥6 s per host, back-off, no browser disguise) | [`ingest.py`](src/bazarpulse/ingest.py), [`fetch.py`](src/bazarpulse/fetch.py) |
| Parse | Finds columns by **header text**, skips the repeated mid-sheet header, ignores the second "changes" table, treats `0` as "not in market" | [`parse.py`](src/bazarpulse/parse.py) |
| Catalog | Maps every raw Bengali spelling (5 years of renames and typos) to a stable product id; unknown spellings are reported, never guessed | [`catalog.py`](src/bazarpulse/catalog.py), [`catalog/`](catalog/) |
| Validate | Pandera data contract + day checks (≥40 products, >50% jumps, cross-file "1 week ago" check) | [`validate.py`](src/bazarpulse/validate.py) |
| Features | Lags, momentum, volatility, days since last change, **days to Ramadan / Eid** (Hijri calendar). Only data known at forecast time | [`features.py`](src/bazarpulse/features.py), [`hijri.py`](src/bazarpulse/hijri.py) |
| Models | Baselines (no change, drift, 7-day mean) + LightGBM candidates; rolling-origin backtest that never trains on the future | [`models.py`](src/bazarpulse/models.py), [`train.py`](src/bazarpulse/train.py) |
| Registry | Champion / previous / decision log in git; every run logged to MLflow | [`registry.py`](src/bazarpulse/registry.py), [`tracking.py`](src/bazarpulse/tracking.py) |
| Monitor | Live error vs backtest, automatic rollback, PSI drift per category, Telegram alerts | [`monitor.py`](src/bazarpulse/monitor.py), [`alerts.py`](src/bazarpulse/alerts.py) |
| Serve | FastAPI (DuckDB SQL over Parquet) in Docker; Streamlit dashboard | [`api/`](api/), [`dashboard/`](dashboard/) |

<!-- RESULTS -->

## Data

Source: [tcb.gov.bd → দৈনিক খুচরা বাজার দর](https://tcb.gov.bd/pages/daily-rmps), one Excel file per day
since May 2021. Raw files are kept unmodified in [`data/raw/`](data/raw/) with a SHA-256 manifest.

Format drift handled by the parser (all covered by tests on real files):

- sheet renamed (`Daily Report` → `Daily retail price`), header row moved
- a **repeated page header mid-sheet**, sometimes with a different date than the first one
- a second "price changes" table below the main one that repeats products
- section-heading rows, `#DIV/0!` cells, `0` for "not available", Bengali/ASCII digits mixed
- products renamed over time (e.g. "পাইজাম/লতা" → "পাইজাম/আটাশ") and TCB typos

See [`reports/data_quality.md`](reports/data_quality.md) for the current numbers.

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | pipeline status, model version, live model health |
| `GET /products` | products with today's price |
| `GET /forecast/{product_id}` | 7-day forecast for one product |
| `GET /movers?limit=10` | largest expected rises and falls |
| `GET /history/{product_id}?days=90` | price history (DuckDB SQL over Parquet) |
| `GET /metrics?days=30` | live accuracy per day, model vs no-change baseline |

Interactive docs at `/docs`.

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt -e .

python -m bazarpulse.ingest            # download new TCB files (--all for the full archive)
python -m bazarpulse.build             # parse into data/clean/
python -m bazarpulse.validate          # data quality report
python -m bazarpulse.train --initial   # backtest candidates, register the champion
python -m bazarpulse.pipeline --refresh  # score, forecast, write status

pytest                                 # tests
uvicorn api.main:app --reload          # API on http://127.0.0.1:8000/docs
streamlit run dashboard/streamlit_app.py
```

## Deploy (all free)

| Piece | Where | How |
|---|---|---|
| Daily pipeline + weekly retrain | GitHub Actions | Already configured in [`.github/workflows/`](.github/workflows/). Runs on schedule; "Run workflow" to trigger by hand |
| Dashboard | Streamlit Community Cloud | New app → this repo, branch `main`, file `dashboard/streamlit_app.py` |
| API | Render (free web service) | New Web Service → this repo → Docker, Dockerfile path `api/Dockerfile`. Redeploys on every push, so it picks up each day's data |
| Alerts (optional) | Telegram | Repo secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Remote MLflow (optional) | DagsHub | Repo secrets `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` |

## Limitations

- TCB surveys a handful of Dhaka markets; prices elsewhere differ.
- Many prices stay flat for weeks, so "no change" is a strong baseline. Results are reported
  against it honestly, per product.
- Ramadan/Eid dates use the Umm al-Qura calendar; Bangladesh often observes them a day later.
- Forecasts are estimates for information, **not official prices** and not financial advice.

## Author

**Sakib Raihan** · [@Sakib9797](https://github.com/Sakib9797)
