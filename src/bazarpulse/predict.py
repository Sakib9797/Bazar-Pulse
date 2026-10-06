"""Daily batch forecast with the champion model.

Writes data/forecasts/<origin date>.parquet (kept for scoring later) and
data/forecasts/latest.json (read by the API and the dashboard).
"""
import json
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from bazarpulse import catalog, features, models, registry
from bazarpulse.build import PRICES

FORECASTS = os.path.join("data", "forecasts")
LATEST = os.path.join(FORECASTS, "latest.json")


def run(as_of=None, log=print):
    products = catalog.load_products()
    prices = pd.read_parquet(PRICES)
    prices = prices[prices["product_id"].isin(products)]
    booster, champ = registry.load_champion()
    rows = features.forecast_rows(prices, products, as_of)
    if rows.empty:
        raise RuntimeError("no products have a recent enough price to forecast")

    last_price = np.exp(rows["log_price"].to_numpy())
    pred = last_price * np.exp(models.predict(booster, rows))
    out = pd.DataFrame({
        "origin_date": rows["date"], "target_date": rows["target_date"], "h": rows["h"],
        "product_id": rows["product_id"].astype(str), "last_price": last_price.round(2),
        "pred_price": pred.round(2), "pred_change_pct": ((pred / last_price - 1) * 100).round(2),
        "last_seen": rows["last_seen"], "model_version": champ["version"],
    })
    origin = out["origin_date"].max()
    os.makedirs(FORECASTS, exist_ok=True)
    out.to_parquet(os.path.join(FORECASTS, f"{origin:%Y-%m-%d}.parquet"), index=False)
    _write_latest(out, products, champ, origin)
    log(f"forecast from {origin.date()}: {out['product_id'].nunique()} products x 7 days "
        f"(model v{champ['version']})")
    return out


def _write_latest(out, products, champ, origin):
    items = []
    for pid, g in out.sort_values("h").groupby("product_id"):
        p = products[pid]
        items.append({
            "product_id": pid, "name_en": p["name_en"], "name_bn": p["name_bn"],
            "category": p["category"], "unit": p["unit_en"],
            "last_price": float(g["last_price"].iloc[0]), "last_seen": f"{g['last_seen'].iloc[0]:%Y-%m-%d}",
            "forecast": [{"date": f"{r.target_date:%Y-%m-%d}", "h": int(r.h), "price": float(r.pred_price),
                          "change_pct": float(r.pred_change_pct)} for r in g.itertuples()],
        })
    doc = {"origin_date": f"{origin:%Y-%m-%d}", "model_version": champ["version"],
           "model": champ["config"]["name"], "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
           "source": "Trading Corporation of Bangladesh (TCB) daily retail prices, Dhaka",
           "products": items}
    with open(LATEST, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
