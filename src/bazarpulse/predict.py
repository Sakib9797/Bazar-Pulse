"""Daily batch forecast: low / likely / high price 1-4 weeks ahead for every product.

Writes data/forecasts/<origin date>.parquet (kept for scoring later, including the
climatology baseline's range so live accuracy can be compared fairly) and
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
    model, champ = registry.load_champion()
    rows = features.forecast_rows(prices, products, as_of)
    if rows.empty:
        raise RuntimeError("no products have a recent enough price to forecast")

    origin = rows["date"].max()
    history = features.training_rows(prices, products)
    clim = models.climatology(history, rows, origin + pd.Timedelta(days=1))
    q = clim if model is None else models.predict(model, rows)
    last = np.exp(rows["log_price"].to_numpy())

    def price(x):
        return (last * np.exp(x.to_numpy())).round(2)

    out = pd.DataFrame({
        "origin_date": rows["date"], "target_date": rows["target_date"], "h": rows["h"],
        "product_id": rows["product_id"].astype(str), "last_price": last.round(2),
        "low": price(q["lo"]), "mid": price(q["mid"]), "high": price(q["hi"]),
        "clim_low": price(clim["lo"]), "clim_mid": price(clim["mid"]), "clim_high": price(clim["hi"]),
        "last_seen": rows["last_seen"], "model_version": champ["version"],
    })
    os.makedirs(FORECASTS, exist_ok=True)
    out.to_parquet(os.path.join(FORECASTS, f"{origin:%Y-%m-%d}.parquet"), index=False)
    _write_latest(out, products, champ, origin)
    log(f"forecast from {origin.date()}: {out['product_id'].nunique()} products x "
        f"{len(features.HORIZONS)} horizons (champion v{champ['version']}, {champ['config']['name']})")
    return out


def _write_latest(out, products, champ, origin):
    items = []
    for pid, g in out.sort_values("h").groupby("product_id"):
        p = products[pid]
        last = float(g["last_price"].iloc[0])
        items.append({
            "product_id": pid, "name_en": p["name_en"], "name_bn": p["name_bn"],
            "category": p["category"], "unit": p["unit_en"],
            "last_price": last, "last_seen": f"{g['last_seen'].iloc[0]:%Y-%m-%d}",
            "forecast": [{"date": f"{r.target_date:%Y-%m-%d}", "weeks": int(r.h) // 7,
                          "low": float(r.low), "mid": float(r.mid), "high": float(r.high),
                          "change_pct": round((r.mid / last - 1) * 100, 2),
                          "upside_pct": round((r.high / last - 1) * 100, 2)} for r in g.itertuples()],
        })
    doc = {"origin_date": f"{origin:%Y-%m-%d}", "model_version": champ["version"],
           "model": champ["config"]["name"], "coverage_target": models.COVERAGE,
           "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
           "source": "Trading Corporation of Bangladesh (TCB) daily retail prices, Dhaka",
           "products": items}
    with open(LATEST, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
