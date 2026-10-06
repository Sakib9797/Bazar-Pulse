"""Live monitoring: score past forecasts against real prices, check drift, roll back.

    data/monitoring/scores.parquet         one row per scored forecast
    data/monitoring/daily_metrics.parquet  live MAPE per target day (model vs naive)
    data/monitoring/health.json            14-day live accuracy vs the backtest promise
    data/monitoring/drift.json             PSI of recent weekly price changes per category
"""
import glob
import json
import os

import numpy as np
import pandas as pd

from bazarpulse import alerts, catalog, registry
from bazarpulse.build import PRICES

MON = os.path.join("data", "monitoring")
SCORES = os.path.join(MON, "scores.parquet")
DAILY = os.path.join(MON, "daily_metrics.parquet")
HEALTH = os.path.join(MON, "health.json")
DRIFT = os.path.join(MON, "drift.json")
LIVE_WINDOW_DAYS = 14
MIN_LIVE_ROWS = 100
ROLLBACK_RATIO = 1.3
PSI_ALERT = 0.25
KEY = ["origin_date", "target_date", "product_id"]


def score(log=print):
    prices = pd.read_parquet(PRICES)[["date", "product_id", "price_mid"]]
    files = sorted(glob.glob(os.path.join("data", "forecasts", "*.parquet")))
    if not files:
        return pd.DataFrame()
    fc = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    done = pd.read_parquet(SCORES) if os.path.exists(SCORES) else pd.DataFrame(columns=KEY)

    cand = fc.merge(prices, left_on=["target_date", "product_id"], right_on=["date", "product_id"])
    if not done.empty:
        cand = cand.merge(done[KEY], on=KEY, how="left", indicator=True)
        cand = cand[cand["_merge"] == "left_only"].drop(columns="_merge")
    if cand.empty:
        log("monitor: no newly scorable forecasts")
        return done
    cand = cand.rename(columns={"price_mid": "actual"})
    cand["ape_model"] = (cand["pred_price"] - cand["actual"]).abs() / cand["actual"]
    cand["ape_naive"] = (cand["last_price"] - cand["actual"]).abs() / cand["actual"]
    new = cand[KEY + ["h", "model_version", "actual", "pred_price", "last_price", "ape_model", "ape_naive"]]
    allscores = pd.concat([done, new], ignore_index=True) if not done.empty else new
    os.makedirs(MON, exist_ok=True)
    allscores.to_parquet(SCORES, index=False)

    daily = (allscores.groupby("target_date")
             .agg(mape_model=("ape_model", "mean"), mape_naive=("ape_naive", "mean"), n=("ape_model", "size"))
             .reset_index())
    daily[["mape_model", "mape_naive"]] *= 100
    daily.to_parquet(DAILY, index=False)
    log(f"monitor: scored {len(new)} new forecast(s); {len(allscores)} in total")
    return allscores


def health(log=print):
    """Compare the champion's live error with its backtest; roll back if it degraded badly."""
    reg = registry.load()
    champ = reg["champion"]
    if not champ or not os.path.exists(SCORES):
        return None
    s = pd.read_parquet(SCORES)
    s = s[s["model_version"] == champ["version"]]
    cutoff = s["target_date"].max() - pd.Timedelta(days=LIVE_WINDOW_DAYS) if len(s) else None
    recent = s[s["target_date"] > cutoff] if cutoff is not None else s
    h = {"champion_version": champ["version"], "backtest_mape": round(champ["backtest"]["mape_model"], 3),
         "live_rows": int(len(recent)), "status": "warming_up"}
    if len(recent) >= MIN_LIVE_ROWS:
        live, naive = recent["ape_model"].mean() * 100, recent["ape_naive"].mean() * 100
        h.update(live_mape=round(live, 3), live_naive_mape=round(naive, 3),
                 ratio_to_backtest=round(live / champ["backtest"]["mape_model"], 3), status="ok")
        if live > ROLLBACK_RATIO * champ["backtest"]["mape_model"]:
            h["status"] = "degraded"
            if reg["previous"]:
                back = registry.rollback(f"live MAPE {live:.2f}% > {ROLLBACK_RATIO}x backtest "
                                         f"{champ['backtest']['mape_model']:.2f}%")
                h["status"] = f"rolled_back_to_v{back['version']}"
                alerts.send(f"Model v{champ['version']} degraded (live MAPE {live:.2f}%). "
                            f"Rolled back to v{back['version']}.", "error")
            else:
                alerts.send(f"Model v{champ['version']} degraded (live MAPE {live:.2f}%) and there "
                            "is no previous version to roll back to.", "error")
    os.makedirs(MON, exist_ok=True)
    with open(HEALTH, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=2)
    log(f"monitor: health {h['status']} ({h['live_rows']} live rows)")
    return h


# Fixed bins on 7-day log change. Most weeks a price does not move at all, so quantile
# bins collapse onto zero; fixed bins (big fall .. flat .. big rise) stay meaningful.
PSI_EDGES = np.array([-np.inf, -0.10, -0.05, -0.02, -0.005, 0.005, 0.02, 0.05, 0.10, np.inf])


def _psi(ref, cur, edges=PSI_EDGES):
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def drift(log=print):
    """PSI of 7-day log price changes: last 28 days vs the year before that, per category."""
    products = catalog.load_products()
    p = pd.read_parquet(PRICES)
    p = p[p["product_id"].isin(products)].sort_values("date")
    w = np.log(p.pivot_table(index="date", columns="product_id", values="price_mid"))
    w = w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="D")).ffill(limit=21)
    r7 = (w - w.shift(7)).stack().rename("r7").reset_index()
    r7.columns = ["date", "product_id", "r7"]
    r7["category"] = r7["product_id"].map(lambda x: products[x]["category"])
    end = r7["date"].max()
    cur_mask = r7["date"] > end - pd.Timedelta(days=28)
    ref_mask = (r7["date"] <= end - pd.Timedelta(days=28)) & (r7["date"] > end - pd.Timedelta(days=28 + 365))
    out = {}
    for cat, g in r7.groupby("category"):
        ref, cur = g.loc[ref_mask[g.index], "r7"], g.loc[cur_mask[g.index], "r7"]
        if len(ref) > 200 and len(cur) > 30:
            out[cat] = round(_psi(ref.to_numpy(), cur.to_numpy()), 3)
    drifted = {k: v for k, v in out.items() if v > PSI_ALERT}
    doc = {"as_of": f"{end:%Y-%m-%d}", "psi": out, "threshold": PSI_ALERT, "drifted": sorted(drifted)}
    os.makedirs(MON, exist_ok=True)
    with open(DRIFT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    log(f"monitor: drift PSI {out}")
    return doc
