"""Bazar Pulse API: 1-4 week price ranges and price history for Dhaka's essential goods.

    uvicorn api.main:app --reload
"""
import json
import os

import duckdb
from fastapi import FastAPI, HTTPException, Query

DATA = os.environ.get("BAZARPULSE_DATA", "data")
LATEST = os.path.join(DATA, "forecasts", "latest.json")
PRICES = os.path.join(DATA, "clean", "prices.parquet").replace("\\", "/")
DAILY = os.path.join(DATA, "monitoring", "daily_metrics.parquet").replace("\\", "/")
HEALTH = os.path.join(DATA, "monitoring", "health.json")
STATUS = os.path.join(DATA, "status.json")

app = FastAPI(
    title="Bazar Pulse API",
    version="0.1.0",
    description="1-4 week price ranges (low / likely / high, 80% range) for Dhaka's essential goods, "
                "built from the Trading Corporation of Bangladesh (TCB) daily retail price sheets. "
                "Not an official source.",
)
_cache = {}


def _json(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _cache.get(path, (None,))[0] != mtime:
        with open(path, encoding="utf-8") as f:
            _cache[path] = (mtime, json.load(f))
    return _cache[path][1]


def _latest():
    doc = _json(LATEST)
    if doc is None:
        raise HTTPException(503, "no forecast available yet")
    return doc


def _summary(p):
    keys = ("product_id", "name_en", "name_bn", "category", "unit", "last_price", "last_seen")
    return {k: p[k] for k in keys}


@app.get("/health")
def health():
    doc = _json(LATEST) or {}
    return {"status": "ok" if doc else "no_forecast", "origin_date": doc.get("origin_date"),
            "model_version": doc.get("model_version"), "pipeline": _json(STATUS),
            "model_health": _json(HEALTH)}


@app.get("/products")
def products(category: str | None = None):
    items = _latest()["products"]
    return [_summary(p) for p in items if category is None or p["category"] == category]


@app.get("/forecast")
def forecast_all(category: str | None = None):
    doc = _latest()
    items = [p for p in doc["products"] if category is None or p["category"] == category]
    return {**{k: v for k, v in doc.items() if k != "products"}, "products": items}


@app.get("/forecast/{product_id}")
def forecast(product_id: str):
    doc = _latest()
    for p in doc["products"]:
        if p["product_id"] == product_id:
            return {"origin_date": doc["origin_date"], "model_version": doc["model_version"], **p}
    raise HTTPException(404, f"unknown product_id '{product_id}'")


@app.get("/movers")
def movers(limit: int = Query(10, ge=1, le=50)):
    """At the 4-week horizon: largest likely rises and falls, and the largest upside risk
    (top of the 80% range)."""
    rows = []
    for p in _latest()["products"]:
        f = p["forecast"][-1]
        rows.append({**_summary(p), "date": f["date"], "weeks": f["weeks"], "low": f["low"], "mid": f["mid"],
                     "high": f["high"], "change_pct": f["change_pct"], "upside_pct": f["upside_pct"]})
    by_change = sorted(rows, key=lambda r: r["change_pct"])
    return {"rises": by_change[::-1][:limit], "falls": by_change[:limit],
            "upside_risk": sorted(rows, key=lambda r: r["upside_pct"], reverse=True)[:limit]}


@app.get("/history/{product_id}")
def history(product_id: str, days: int = Query(90, ge=1, le=2000)):
    if not os.path.exists(PRICES):
        raise HTTPException(503, "no price data available")
    rows = duckdb.execute(
        f"""
        SELECT strftime(date, '%Y-%m-%d') AS date, price_min, price_max, price_mid
        FROM read_parquet('{PRICES}')
        WHERE product_id = ?
          AND date > (SELECT max(date) FROM read_parquet('{PRICES}')) - to_days(?)
        ORDER BY date
        """, [product_id, days]).fetchall()
    if not rows:
        raise HTTPException(404, f"no history for '{product_id}'")
    return {"product_id": product_id,
            "prices": [dict(zip(("date", "min", "max", "mid"), r, strict=True)) for r in rows]}


@app.get("/metrics")
def metrics(days: int = Query(30, ge=1, le=365)):
    """Live accuracy per day: pinball loss vs the climatology baseline, and how often the
    real price fell inside the forecast's 80% range."""
    cols = ("date", "pinball_model", "pinball_climatology", "coverage", "coverage_climatology", "n")
    daily = []
    if os.path.exists(DAILY):
        daily = duckdb.execute(
            f"""
            SELECT strftime(target_date, '%Y-%m-%d'), round(pinball_model, 4), round(pinball_climatology, 4),
                   round(coverage, 3), round(coverage_climatology, 3), n
            FROM read_parquet('{DAILY}')
            ORDER BY target_date DESC LIMIT ?
            """, [days]).fetchall()
    return {"health": _json(HEALTH), "daily": [dict(zip(cols, r, strict=True)) for r in daily]}
