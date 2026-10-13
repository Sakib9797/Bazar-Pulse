"""Live monitoring: score past forecasts against real prices, check drift, roll back.

    data/monitoring/scores.parquet         one row per scored forecast (model and baseline)
    data/monitoring/daily_metrics.parquet  live pinball loss and range coverage per target day
    data/monitoring/health.json            last 28 days of live accuracy vs the backtest promise
    data/monitoring/drift.json             PSI of recent weekly price changes vs each category's normal
"""
import glob
import json
import os

import numpy as np
import pandas as pd

from bazarpulse import alerts, catalog, models, registry
from bazarpulse.build import PRICES

MON = os.path.join("data", "monitoring")
SCORES = os.path.join(MON, "scores.parquet")
DAILY = os.path.join(MON, "daily_metrics.parquet")
HEALTH = os.path.join(MON, "health.json")
DRIFT = os.path.join(MON, "drift.json")
LIVE_WINDOW_DAYS = 28
MIN_LIVE_ROWS = 100
ROLLBACK_RATIO = 1.3
LOW_COVERAGE = 0.65
DRIFT_WINDOW = 28
DRIFT_PCT = 0.95
KEY = ["origin_date", "target_date", "product_id"]


def _log_ratio(x, last):
    return np.log(x / last)


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
    c = cand.rename(columns={"price_mid": "actual"})
    last = c["last_price"]
    y = _log_ratio(c["actual"], last)
    c["pinball"] = models.pinball(y, _log_ratio(c["low"], last), _log_ratio(c["mid"], last),
                                  _log_ratio(c["high"], last))
    c["pinball_clim"] = models.pinball(y, _log_ratio(c["clim_low"], last), _log_ratio(c["clim_mid"], last),
                                       _log_ratio(c["clim_high"], last))
    c["covered"] = (c["actual"] >= c["low"]) & (c["actual"] <= c["high"])
    c["covered_clim"] = (c["actual"] >= c["clim_low"]) & (c["actual"] <= c["clim_high"])
    c["ape_mid"] = (c["mid"] - c["actual"]).abs() / c["actual"]
    c["ape_naive"] = (last - c["actual"]).abs() / c["actual"]
    new = c[KEY + ["h", "model_version", "actual", "last_price", "low", "mid", "high", "pinball",
                   "pinball_clim", "covered", "covered_clim", "ape_mid", "ape_naive"]]
    allscores = pd.concat([done, new], ignore_index=True) if not done.empty else new
    os.makedirs(MON, exist_ok=True)
    allscores.to_parquet(SCORES, index=False)

    daily = (allscores.groupby("target_date")
             .agg(pinball_model=("pinball", "mean"), pinball_climatology=("pinball_clim", "mean"),
                  coverage=("covered", "mean"), coverage_climatology=("covered_clim", "mean"),
                  mape_mid=("ape_mid", "mean"), mape_naive=("ape_naive", "mean"), n=("pinball", "size"))
             .reset_index())
    for col in ("pinball_model", "pinball_climatology", "mape_mid", "mape_naive"):
        daily[col] *= 100
    daily.to_parquet(DAILY, index=False)
    log(f"monitor: scored {len(new)} new forecast(s); {len(allscores)} in total")
    return allscores


def health(log=print):
    """Compare the champion's live accuracy with its backtest; roll back if it degraded badly."""
    reg = registry.load()
    champ = reg["champion"]
    if not champ or not os.path.exists(SCORES):
        return None
    previous = {}
    if os.path.exists(HEALTH):
        with open(HEALTH, encoding="utf-8") as f:
            previous = json.load(f)
    s = pd.read_parquet(SCORES)
    s = s[s["model_version"] == champ["version"]]
    if len(s):
        s = s[s["target_date"] > s["target_date"].max() - pd.Timedelta(days=LIVE_WINDOW_DAYS)]
    recent = s
    promised = champ["backtest"]["pinball_model"]
    h = {"champion_version": champ["version"], "model": champ["config"]["name"],
         "backtest_pinball": round(promised, 4),
         "backtest_coverage": round(champ["backtest"]["coverage_model"], 3),
         "live_rows": int(len(recent)), "status": "warming_up"}
    if len(recent) >= MIN_LIVE_ROWS:
        live = recent["pinball"].mean() * 100
        h.update(live_pinball=round(live, 4),
                 live_pinball_climatology=round(recent["pinball_clim"].mean() * 100, 4),
                 live_coverage=round(float(recent["covered"].mean()), 3),
                 ratio_to_backtest=round(live / promised, 3), status="ok")
        if h["live_coverage"] < LOW_COVERAGE:
            h["status"] = "low_coverage"
        if live > ROLLBACK_RATIO * promised:
            h["status"] = "degraded"
            if reg["previous"]:
                back = registry.rollback(
                    f"live pinball {live:.4f} > {ROLLBACK_RATIO}x backtest {promised:.4f}")
                h["status"] = f"rolled_back_to_v{back['version']}"
    if h["status"] != previous.get("status") and h["status"] not in ("ok", "warming_up"):
        level = "error" if h["status"] != "low_coverage" else "warning"
        alerts.send(f"Model v{champ['version']} health is now '{h['status']}': live pinball "
                    f"{h.get('live_pinball')} vs backtest {promised:.4f}, range coverage "
                    f"{h.get('live_coverage')} (target {models.COVERAGE}).", level)
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


def _window_psi(g, end):
    """PSI of one category's 7-day changes: the 28 days to `end` vs the year before them."""
    cur = g[(g["date"] > end - pd.Timedelta(days=DRIFT_WINDOW)) & (g["date"] <= end)]["r7"]
    ref = g[(g["date"] <= end - pd.Timedelta(days=DRIFT_WINDOW))
            & (g["date"] > end - pd.Timedelta(days=DRIFT_WINDOW + 365))]["r7"]
    if len(ref) <= 200 or len(cur) <= 30:
        return None
    return _psi(ref.to_numpy(), cur.to_numpy())


def drift(log=print):
    """Is this month's price behaviour unusual for its category?

    PSI of 7-day log price changes (last 28 days vs the year before). TCB prices drift a lot
    by nature: the textbook 0.25 threshold was exceeded in 45-100% of past windows. So each
    category is compared with its OWN history: drift is flagged when the current PSI is above
    the DRIFT_PCT quantile of that category's PSI over the previous two years.
    """
    products = catalog.load_products()
    p = pd.read_parquet(PRICES)
    p = p[p["product_id"].isin(products)].sort_values("date")
    w = np.log(p.pivot_table(index="date", columns="product_id", values="price_mid"))
    w = w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="D")).ffill(limit=21)
    r7 = (w - w.shift(7)).stack().rename("r7").reset_index()
    r7.columns = ["date", "product_id", "r7"]
    r7["category"] = r7["product_id"].map(lambda x: products[x]["category"])
    end = r7["date"].max()
    past_ends = pd.date_range(end - pd.Timedelta(days=730), end - pd.Timedelta(days=DRIFT_WINDOW), freq="14D")
    psi, thresholds = {}, {}
    for cat, g in r7.groupby("category"):
        now = _window_psi(g, end)
        past = [x for x in (_window_psi(g, e) for e in past_ends) if x is not None]
        if now is None or len(past) < 20:
            continue
        psi[cat] = round(now, 3)
        thresholds[cat] = round(float(np.quantile(past, DRIFT_PCT)), 3)
    drifted = sorted(c for c in psi if psi[c] > thresholds[c])
    doc = {"as_of": f"{end:%Y-%m-%d}", "psi": psi, "thresholds": thresholds, "drifted": drifted,
           "method": f"PSI of 7-day changes, last {DRIFT_WINDOW} days vs previous year; threshold = "
                     f"{DRIFT_PCT:.0%} quantile of the category's own PSI over the last two years"}
    os.makedirs(MON, exist_ok=True)
    with open(DRIFT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    log(f"monitor: drift {len(drifted)} unusual of {len(psi)} categories {drifted}")
    return doc
