"""Turn the daily price table into model rows.

One row = (product, origin date t, horizon h). Every feature uses prices known on or
before t only; the target is the log price change from t to t+h, where t+h must be a
day TCB actually published that product. Gaps (Fridays, holidays) are bridged by
carrying the last price forward for at most FFILL_LIMIT days when computing
features, never when computing targets.
"""
import numpy as np
import pandas as pd

from bazarpulse.hijri import calendar_features

HORIZONS = (7, 14, 21, 28)
FFILL_LIMIT = 21
FEATURES = ["h", "product", "category", "r1", "r7", "r14", "r28", "r56", "vol28",
            "ma7_gap", "ma28_gap", "days_since_change", "spread", "cat_r7", "ly_h",
            "dow", "month", "in_ramadan", "days_to_ramadan", "days_to_eid_fitr", "days_to_eid_adha"]
CATEGORICAL = ["product", "category"]


def _wide(prices, value):
    w = prices.pivot_table(index="date", columns="product_id", values=value, aggfunc="last")
    full = pd.date_range(w.index.min(), w.index.max(), freq="D", name="date")
    return w.reindex(full)


def origin_features(prices, products):
    """Feature frame for every (date, product) with a price on or shortly before that date."""
    obs = np.log(_wide(prices, "price_mid"))
    lp = obs.ffill(limit=FFILL_LIMIT)
    spread = ((_wide(prices, "price_max") - _wide(prices, "price_min")) / _wide(prices, "price_mid"))
    spread = spread.ffill(limit=FFILL_LIMIT)

    r7 = lp - lp.shift(7)
    # Mean 7-day move of the product's category (edible oils, rice... tend to move together).
    cat_of = {pid: products[pid]["category"] for pid in lp.columns}
    cat_mean = r7.T.groupby(cat_of).mean().T
    cat_r7 = cat_mean[[cat_of[c] for c in lp.columns]].set_axis(lp.columns, axis=1)

    daily = lp.diff()
    changed = daily.fillna(0).ne(0)
    since_change = changed.apply(lambda c: c.groupby(c.cumsum()).cumcount())

    parts = {
        "log_price": lp,
        "observed": obs.notna(),
        **{f"r{k}": lp - lp.shift(k) for k in (1, 7, 14, 28, 56)},
        "vol28": daily.rolling(28, min_periods=10).std(),
        "ma7_gap": lp.rolling(7, min_periods=3).mean() - lp,
        "ma28_gap": lp.rolling(28, min_periods=10).mean() - lp,
        "days_since_change": since_change.where(lp.notna()),
        "spread": spread,
        "cat_r7": cat_r7,
        # Same-season analogue: how the price moved over the next k days one year earlier.
        **{f"ly{k}": lp.shift(365 - k) - lp.shift(365) for k in HORIZONS},
    }
    long = pd.concat({k: v.stack(future_stack=True) for k, v in parts.items()}, axis=1)
    long.index.names = ["date", "product_id"]
    long = long[long["log_price"].notna()].reset_index()
    long["observed"] = long["observed"].astype(bool)
    return long, obs


def _categorise(df, products):
    cats = sorted(products)
    df["product"] = pd.Categorical(df["product_id"], categories=cats)
    groups = sorted({p["category"] for p in products.values()})
    df["category"] = pd.Categorical(df["product_id"].map(lambda p: products[p]["category"]),
                                    categories=groups)
    return df


def _with_horizon(origins, h):
    rows = origins.copy()
    rows["h"] = h
    rows["target_date"] = rows["date"] + pd.Timedelta(days=h)
    rows["ly_h"] = rows[f"ly{h}"]
    rows = rows.drop(columns=[f"ly{k}" for k in HORIZONS])
    cal = calendar_features(rows["target_date"])
    cal.index = rows.index
    return pd.concat([rows, cal], axis=1)


def training_rows(prices, products):
    """All (origin, horizon) rows whose target day has a real TCB price."""
    origins, obs = origin_features(prices, products)
    origins = origins[origins["observed"]]
    target = obs.stack(future_stack=True).rename("target_log").dropna()
    out = []
    for h in HORIZONS:
        rows = _with_horizon(origins, h)
        rows = rows.join(target, on=["target_date", "product_id"], how="inner")
        out.append(rows)
    df = pd.concat(out, ignore_index=True)
    df["y"] = df["target_log"] - df["log_price"]
    return _categorise(df, products)


def forecast_rows(prices, products, as_of=None, max_staleness=14):
    """Rows for predicting h = 1..7 days after `as_of` (default: latest report date)."""
    origins, _ = origin_features(prices, products)
    as_of = pd.Timestamp(as_of) if as_of is not None else prices["date"].max()
    last_seen = prices.groupby("product_id")["date"].max()
    fresh = last_seen[last_seen >= as_of - pd.Timedelta(days=max_staleness)].index
    at = origins[(origins["date"] == as_of) & origins["product_id"].isin(fresh)]
    rows = pd.concat([_with_horizon(at, h) for h in HORIZONS], ignore_index=True)
    rows = rows.merge(last_seen.rename("last_seen").reset_index(), on="product_id")
    return _categorise(rows, products)
