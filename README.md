# 🛒 Bazar Pulse

**Where will Dhaka's essential-goods prices be in 1–4 weeks?** A self-running forecasting
system built on the official daily retail price sheets of the Trading Corporation of
Bangladesh (TCB).

Every day it downloads TCB's new price sheet, validates it, checks earlier forecasts against
the real prices, and publishes a **likely price range** (low / likely / high) 1, 2, 3 and 4
weeks ahead for ~60 products: rice, onion, eggs, oil, lentils, sugar, fish, meat and more.
Every week it trains challenger models and replaces the champion **only if a challenger is
measurably better**. If live accuracy degrades, it rolls back to the previous model on its own.

> The point of this project is the MLOps: a pipeline that runs, validates, monitors,
> retrains and alerts without anyone touching it, and that is honest about what can and
> cannot be predicted.

<!-- Add your live links here after deploying, e.g.
**Live dashboard:** https://<your-app>.streamlit.app · **API:** https://<your-api>.onrender.com/docs -->

---

## Why this data

- **Real impact.** Onion, egg and oil price spikes are national news in Bangladesh.
- **Ground truth arrives every day.** Later TCB sheets show whether a forecast was right, so
  the system monitors **real** accuracy, not proxies.
- **Messy, real-world input.** Bengali Excel files whose layout drifted over 5 years (see
  [Data](#data)), which makes data validation and contracts essential.

## How it works

```
                 ┌──────── daily, 14:00 Bangladesh time (GitHub Actions) ─────────────┐
TCB daily Excel ─▶ fetch ─▶ parse ─▶ validate ─▶ store (Parquet in git)                  │
                 │                      │ hard failure: stop, alert, keep last good      │
                 │ score earlier forecasts against today's real prices                  │
                 │ health check (rollback if live loss > 1.3× backtest) + drift check    │
                 │ forecast 1-4 week ranges with the champion ─▶ commit ─▶ API/dashboard  │
                 └────────────────────────────────────────────────────────────────────────┘
                 ┌──────── weekly (GitHub Actions) ───────────────────────────────────────┐
                 │ backtest every candidate on the last 8 weeks (MLflow-tracked)          │
                 │ switch champion only if ≥2% better AND better than the baseline        │
                 └────────────────────────────────────────────────────────────────────────┘
```

| Stage | What it does | Code |
|---|---|---|
| Fetch | Walks TCB's paginated archive, downloads new Excel files politely (≥6 s per host, back-off, no browser disguise) | [`ingest.py`](src/bazarpulse/ingest.py), [`fetch.py`](src/bazarpulse/fetch.py) |
| Parse | Finds columns by **header text**, tries every sheet, skips the repeated mid-sheet header, ignores the second "changes" table, treats `0` as "not in market" | [`parse.py`](src/bazarpulse/parse.py) |
| Catalog | Maps every raw Bengali spelling (5 years of renames, seasonal labels and typos) to a stable product id; unknown spellings are reported, never guessed | [`catalog.py`](src/bazarpulse/catalog.py), [`catalog/`](catalog/) |
| Validate | Pandera data contract + day checks (≥40 products, >50% jumps, cross-file "1 week ago" check) | [`validate.py`](src/bazarpulse/validate.py) |
| Features | Momentum, volatility, days since last change, category moves, same week last year, **days to Ramadan / Eid** (Hijri calendar). Only data known at forecast time | [`features.py`](src/bazarpulse/features.py), [`hijri.py`](src/bazarpulse/hijri.py) |
| Models | Quantile LightGBM (10% / 50% / 90%) + conformal calibration; climatology baseline; rolling-origin backtest that never trains on the future | [`models.py`](src/bazarpulse/models.py), [`train.py`](src/bazarpulse/train.py) |
| Registry | Champion / previous / decision log in git; every run logged to MLflow | [`registry.py`](src/bazarpulse/registry.py), [`tracking.py`](src/bazarpulse/tracking.py) |
| Monitor | Live loss and range coverage vs backtest, automatic rollback, drift vs each category's normal, Telegram alerts | [`monitor.py`](src/bazarpulse/monitor.py), [`alerts.py`](src/bazarpulse/alerts.py) |
| Serve | FastAPI (DuckDB SQL over Parquet) in Docker; Streamlit dashboard | [`api/`](api/), [`dashboard/`](dashboard/) |

## Results

### What did not work: exact-price forecasts

The first design forecast one exact price 1–7 days ahead. On a 26-week backtest, **no model
beat "the price stays the same"**: the best LightGBM had 0.945% average error vs 0.937% for
no-change, beat it on 0 of 59 products, and called the direction of moves right 48% of the time.
The reason is in the data: in **85% of cases a TCB price does not change at all** within the
forecast window. Longer horizons (14 and 28 days) did not change this.

### What does work: calibrated ranges

So the product forecasts a **range**. Quantile LightGBM predicts the 10th, 50th and 90th
percentile of the price change; the 10–90% range is then calibrated with conformalised
quantile regression (fit on all but the last 8 weeks, then widen or narrow the range so it
would have contained 80% of those held-out prices). The baseline it must beat is
**climatology**: each product's own range of price changes over the previous year.

26-week rolling backtest (April–September 2026), horizons 1–4 weeks
([full report](reports/backtest.md)):

| Model | Pinball loss ↓ | vs baseline | Real price inside the 80% range | Average range width |
|---|---|---|---|---|
| Baseline: climatology | 3.441 | – | 82.0% | 10.6% |
| qlgbm | 3.355 | +2.5% | 80.1% | 8.7% |
| qlgbm_deep | 3.396 | +1.3% | 79.6% | 8.5% |
| **qlgbm_smooth (champion)** | **3.334** | **+3.1%** | **81.3%** | **8.7%** |

By horizon the champion is +5.2% (1 week), +2.8% (2), +2.3% (3) and +3.0% (4) better than the
baseline: **narrower ranges with the same coverage**. Without calibration the ranges covered
only ~70%.

**Honest limits.** The gain is modest and uneven: the model wins on 28 of 59 products. The
most volatile vegetables are under-covered (green chili 40%, cucumber 32%) because the
calibration is shared across products. Per-product calibration fixed coverage but made ranges
so wide the model lost to the baseline (−1.3%), so it was not adopted; instead the dashboard
shows each product's backtest coverage and warns when it is low.

### Monitoring decisions backed by data

The textbook drift threshold (PSI > 0.25) was exceeded in 45–100% of past 4-week windows,
because TCB prices drift by nature. An alert that is always on is useless, so each category
is compared with **its own** history: drift is flagged above the 95th percentile of that
category's PSI over the previous two years.

## Data

Source: [tcb.gov.bd → দৈনিক খুচরা বাজার দর](https://tcb.gov.bd/pages/daily-rmps), one Excel file per
day since May 2021. Raw files are kept unmodified in [`data/raw/`](data/raw/) with a SHA-256
manifest. Current numbers: [`reports/data_quality.md`](reports/data_quality.md).

- **1,409 files, 1,408 parsed.** The one failure is a file that is all zero bytes on TCB's own
  server.
- **~75,000 daily prices for 63 products**, May 2021 to today. Cross-check: each file also
  lists the price one week earlier; in weekly samples the median share of products where that
  disagrees with the stored history is 0%.
- **2022 is mostly missing from TCB's archive** (64 report days; nothing from August to
  December 2022). Models only learn from days that exist; gaps are never filled with
  invented prices.

Format drift handled by the parser (covered by tests on real files):

- sheet renamed (`Daily Report` → `Daily retail price`), header row moved
- early-2025 workbooks with an unrelated table in the first sheet and the prices in the third
- a **repeated page header mid-sheet**, sometimes with a different date than the first one
- a second "price changes" table below the main one that repeats products
- section-heading rows, `#DIV/0!` cells, `0` for "not available", Bengali/ASCII digits mixed
- products renamed over time (e.g. "পাইজাম/লতা" → "পাইজাম/আটাশ"), seasonal labels
  ("আদা (দেশী) (নতুন)") and TCB typos, verified never to clash on the same day before merging

## Dashboard

Bilingual (English / বাংলা), works on phones. Run it with `streamlit run dashboard/streamlit_app.py`.

| Tab | What you can do |
|---|---|
| 🧭 Outlook | Pick 1-4 weeks and categories; see every product's likely range; **click a product** for a detail card with its reliability badge |
| 🔎 Product | Zoomable price history with Ramadan / Eid markers, the forecast range, and "same time last year" |
| 🧺 My basket | Edit a shopping list and see today's cost vs the likely, best and worst case in 1-4 weeks, and which items add the most risk |
| 📊 Trends | Compare up to 8 products over 1-5 years, as prices or as an index; see typical inflation per category |
| 🩺 Model health | Live range coverage vs the 80% target, backtest results and every model decision |

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | pipeline status, model version, live model health |
| `GET /products` | products with today's price |
| `GET /forecast/{product_id}` | low / likely / high price 1–4 weeks ahead |
| `GET /movers?limit=10` | largest likely rises and falls, and largest upside risk, at 4 weeks |
| `GET /history/{product_id}?days=90` | price history (DuckDB SQL over Parquet) |
| `GET /metrics?days=30` | live pinball loss and range coverage per day, model vs baseline |

Interactive docs at `/docs`.

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt -e .

python -m bazarpulse.pipeline            # fetch new TCB files, validate, score, forecast
python -m bazarpulse.validate            # data quality report
python -m bazarpulse.train --weekly      # challenger vs champion

pytest                                   # tests
uvicorn api.main:app --reload            # API on http://127.0.0.1:8000/docs
streamlit run dashboard/streamlit_app.py # dashboard on http://localhost:8501
```

The data, the trained champion and the reports are committed, so the API and dashboard work
right after cloning. To rebuild everything from scratch: `python -m bazarpulse.ingest --all`
(about 3 hours, deliberately slow to be polite to TCB's server), `python -m bazarpulse.build
--rebuild`, `python -m bazarpulse.train --initial`, `python -m bazarpulse.pipeline --refresh`.

## Deploy (all free)

| Piece | Where | How |
|---|---|---|
| Daily pipeline + weekly retrain | GitHub Actions | Configured in [`.github/workflows/`](.github/workflows/). Runs on schedule; "Run workflow" to trigger by hand |
| Dashboard | Streamlit Community Cloud | New app → this repo, branch `main`, file `dashboard/streamlit_app.py` |
| API | Render (free web service) | New Web Service → this repo → Docker, Dockerfile path `api/Dockerfile`. Redeploys on every push, so it picks up each day's data |
| Alerts (optional) | Telegram | Repo secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Remote MLflow (optional) | DagsHub | Repo secrets `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` |

## Limitations

- TCB surveys a handful of Dhaka markets; prices elsewhere differ.
- The likely (middle) price is usually today's price. The value is in the range, not the middle.
- Ranges for the most volatile vegetables are too narrow; the dashboard flags them.
- Ramadan/Eid dates use the Umm al-Qura calendar; Bangladesh often observes them a day later.
- Forecasts are estimates for information, **not official prices** and not financial advice.

## Author

**Sakib Raihan** · [@Sakib9797](https://github.com/Sakib9797)
