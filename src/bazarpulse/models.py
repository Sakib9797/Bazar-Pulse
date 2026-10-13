"""Range forecasts: quantile LightGBM with conformal calibration, the climatology baseline,
and the rolling-origin backtest.

A model predicts three quantiles (10%, 50%, 90%) of y = log(price at t+h / price at t).
The 10-90% range is then calibrated with conformalised quantile regression (CQR): the
boosters are fit on every row except those whose target falls in the last CAL_DAYS before
the cutoff; on those held-out rows we measure how far outside the range reality fell and
widen (or narrow) the range per horizon so that it would have covered COVERAGE of them.

Exact-price forecasts were tested first and never beat "price stays the same" (prices are
flat in most weeks), so the product is the calibrated range, and the baseline to beat is
each product's own typical range of changes over the past year ("climatology").
"""
import math

import lightgbm as lgb
import numpy as np
import pandas as pd

from bazarpulse.features import CATEGORICAL, FEATURES

QUANTILES = (0.1, 0.5, 0.9)
COVERAGE = 0.8
CAL_DAYS = 56
CLIM_DAYS = 365
BASE = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200, "feature_fraction": 0.8,
        "bagging_fraction": 0.8, "bagging_freq": 1, "num_boost_round": 400, "seed": 7}
CANDIDATES = [
    {"name": "qlgbm", **BASE},
    {"name": "qlgbm_deep", **BASE, "num_leaves": 63, "learning_rate": 0.03, "num_boost_round": 700},
    {"name": "qlgbm_smooth", **BASE, "num_leaves": 15, "min_data_in_leaf": 500, "num_boost_round": 300},
]
CLIMATOLOGY = {"name": "climatology"}


def _fit_quantiles(rows, config):
    params = {k: v for k, v in config.items() if k not in ("name", "num_boost_round")}
    data = lgb.Dataset(rows[FEATURES], label=rows["y"], categorical_feature=CATEGORICAL, free_raw_data=False)
    return {a: lgb.train({**params, "objective": "quantile", "alpha": a, "verbose": -1}, data,
                         num_boost_round=config["num_boost_round"]) for a in QUANTILES}


def _raw(boosters, rows):
    return {a: b.predict(rows[FEATURES]) for a, b in boosters.items()}


def conformal_offsets(q, rows):
    """Per-horizon CQR offset: the COVERAGE quantile of max(lo - y, y - hi)."""
    score = np.maximum(q[0.1] - rows["y"].to_numpy(), rows["y"].to_numpy() - q[0.9])
    out = {}
    for h, s in pd.Series(score).groupby(rows["h"].to_numpy()):
        n = len(s)
        level = min(1.0, math.ceil((n + 1) * COVERAGE) / n)
        out[int(h)] = float(np.quantile(s, level))
    return out


def fit(rows, config, cutoff=None):
    """Fit boosters on rows known well before `cutoff`, calibrate on the last CAL_DAYS."""
    cutoff = pd.Timestamp(cutoff) if cutoff is not None else rows["target_date"].max() + pd.Timedelta(days=1)
    split = cutoff - pd.Timedelta(days=CAL_DAYS)
    proper = rows[rows["target_date"] < split]
    cal = rows[(rows["target_date"] >= split) & (rows["target_date"] < cutoff)]
    boosters = _fit_quantiles(proper, config)
    offsets = conformal_offsets(_raw(boosters, cal), cal) if len(cal) else {}
    return {"boosters": boosters, "conformal": offsets}


def predict(model, rows):
    """Calibrated log-change quantiles: DataFrame with lo, mid, hi aligned to rows."""
    q = _raw(model["boosters"], rows)
    off = rows["h"].map(model["conformal"]).fillna(0).to_numpy()
    mid = q[0.5]
    lo = np.minimum(q[0.1] - off, mid)
    hi = np.maximum(q[0.9] + off, mid)
    return pd.DataFrame({"lo": lo, "mid": mid, "hi": hi}, index=rows.index)


def climatology(history, rows, cutoff):
    """Baseline quantiles from each product's own changes over the CLIM_DAYS before cutoff.

    Falls back to the product's category, then to all products, when a product has too
    little history at that horizon.
    """
    cutoff = pd.Timestamp(cutoff)
    hist = history[history["target_date"] < cutoff]
    recent = hist[hist["target_date"] >= cutoff - pd.Timedelta(days=CLIM_DAYS)]
    if len(recent) >= 20:
        hist = recent
    out = pd.DataFrame(index=rows.index, columns=["lo", "mid", "hi"], dtype=float)
    for level in (["product_id", "h"], ["category", "h"], ["h"]):
        g = hist.groupby(level, observed=True)["y"]
        counts = g.size()
        keep = counts[counts >= 20].index
        if len(keep) == 0:
            continue
        qs = g.quantile(list(QUANTILES)).unstack().loc[keep]
        qs.columns = ["lo", "mid", "hi"]
        out = out.fillna(rows[level].join(qs, on=level)[["lo", "mid", "hi"]])
    return out.fillna(0.0)


def pinball(y, lo, mid, hi):
    """Sum of pinball losses for the three quantiles, per row."""
    y = np.asarray(y)
    loss = 0
    for a, q in zip(QUANTILES, (lo, mid, hi), strict=True):
        d = y - np.asarray(q)
        loss = loss + np.maximum(a * d, (a - 1) * d)
    return loss


def backtest(rows, config, start, end, refit_every=28, log=print):
    """Refit every `refit_every` days on rows whose target precedes the block; score the block."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    out, block = [], start
    while block <= end:
        block_end = min(block + pd.Timedelta(days=refit_every - 1), end)
        train = rows[rows["target_date"] < block]
        test = rows[(rows["date"] >= block) & (rows["date"] <= block_end)]
        if len(test):
            res = test[["date", "target_date", "h", "product_id", "y"]].copy()
            clim = climatology(train, test, block)
            res[["c_lo", "c_mid", "c_hi"]] = clim.to_numpy()
            if config["name"] == CLIMATOLOGY["name"]:
                res[["lo", "mid", "hi"]] = clim.to_numpy()
            else:
                res[["lo", "mid", "hi"]] = predict(fit(train, config, cutoff=block), test).to_numpy()
            out.append(res)
            log(f"    {config['name']}: block {block.date()}..{block_end.date()} "
                f"train={len(train):,} test={len(test):,}")
        block = block_end + pd.Timedelta(days=1)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def ape(y_hat, y):
    return np.abs(np.exp(np.asarray(y_hat) - np.asarray(y)) - 1)


def _width(lo, hi):
    return float(np.mean(np.exp(hi) - np.exp(lo)) * 100)


def summarize(res):
    """Pinball loss (x100) vs climatology, range coverage and width, and point errors."""
    if res.empty:
        return {}
    pm = pinball(res["y"], res["lo"], res["mid"], res["hi"])
    pc = pinball(res["y"], res["c_lo"], res["c_mid"], res["c_hi"])
    s = {
        "pinball_model": float(pm.mean() * 100), "pinball_climatology": float(pc.mean() * 100),
        "coverage_model": float(((res["y"] >= res["lo"]) & (res["y"] <= res["hi"])).mean()),
        "coverage_climatology": float(((res["y"] >= res["c_lo"]) & (res["y"] <= res["c_hi"])).mean()),
        "width_model": _width(res["lo"], res["hi"]), "width_climatology": _width(res["c_lo"], res["c_hi"]),
        "mape_mid": float(ape(res["mid"], res["y"]).mean() * 100),
        "mape_naive": float(ape(0 * res["y"], res["y"]).mean() * 100),
        "rows": int(len(res)),
    }
    s["skill"] = 1 - s["pinball_model"] / s["pinball_climatology"]
    per = pd.DataFrame({"p": res["product_id"], "m": pm, "c": pc}).groupby("p")[["m", "c"]].mean()
    s["products"] = int(len(per))
    s["products_beating_climatology"] = int((per["m"] < per["c"]).sum())
    for h, g in res.groupby("h"):
        gm = pinball(g["y"], g["lo"], g["mid"], g["hi"]).mean()
        gc = pinball(g["y"], g["c_lo"], g["c_mid"], g["c_hi"]).mean()
        s[f"skill_h{h}"] = float(1 - gm / gc)
        s[f"coverage_h{h}"] = float(((g["y"] >= g["lo"]) & (g["y"] <= g["hi"])).mean())
    return s


def per_product_table(res, products):
    t = pd.DataFrame({"product_id": res["product_id"],
                      "model": pinball(res["y"], res["lo"], res["mid"], res["hi"]) * 100,
                      "climatology": pinball(res["y"], res["c_lo"], res["c_mid"], res["c_hi"]) * 100,
                      "covered": (res["y"] >= res["lo"]) & (res["y"] <= res["hi"])})
    t = t.groupby("product_id").mean()
    t["model_better"] = t["model"] < t["climatology"]
    t["name_en"] = [products[p]["name_en"] for p in t.index]
    return t.sort_values("climatology", ascending=False)
