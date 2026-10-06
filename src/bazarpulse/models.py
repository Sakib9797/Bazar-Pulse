"""Forecasting models (baselines + LightGBM) and the rolling-origin backtest.

Models predict y = log(price at t+h) - log(price at t). The error metric is the
absolute percentage error of the implied price: |exp(y_hat - y) - 1|.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from bazarpulse.features import CATEGORICAL, FEATURES

BASE = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200, "feature_fraction": 0.8,
        "bagging_fraction": 0.8, "bagging_freq": 1, "num_boost_round": 400, "seed": 7}
CANDIDATES = [
    {"name": "lgbm_l1", "objective": "l1", **BASE},
    {"name": "lgbm_huber", "objective": "huber", "alpha": 0.03, **BASE},
    {"name": "lgbm_l1_deep", "objective": "l1", **BASE, "num_leaves": 63, "learning_rate": 0.03,
     "num_boost_round": 700},
]
BASELINES = ["naive", "drift", "ma7"]


def fit(rows, config):
    params = {k: v for k, v in config.items() if k not in ("name", "num_boost_round")}
    params["verbose"] = -1
    data = lgb.Dataset(rows[FEATURES], label=rows["y"], categorical_feature=CATEGORICAL,
                       free_raw_data=False)
    return lgb.train(params, data, num_boost_round=config["num_boost_round"])


def predict(booster, rows):
    return booster.predict(rows[FEATURES])


def baselines(rows):
    """Predicted log change for each baseline. naive = no change."""
    return {
        "naive": np.zeros(len(rows)),
        "drift": (rows["r28"].fillna(0) / 28 * rows["h"]).to_numpy(),
        "ma7": rows["ma7_gap"].fillna(0).to_numpy(),
    }


def ape(y_hat, y):
    return np.abs(np.exp(np.asarray(y_hat) - np.asarray(y)) - 1)


def backtest(rows, config, start, end, refit_every=28, log=print):
    """Refit every `refit_every` days; train only on rows whose TARGET date precedes the block."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    block = start
    while block <= end:
        block_end = min(block + pd.Timedelta(days=refit_every - 1), end)
        train = rows[rows["target_date"] < block]
        test = rows[(rows["date"] >= block) & (rows["date"] <= block_end)]
        if len(test):
            booster = fit(train, config)
            res = test[["date", "target_date", "h", "product_id", "y"]].copy()
            res["model"] = predict(booster, test)
            for name, pred in baselines(test).items():
                res[name] = pred
            out.append(res)
            log(f"    {config['name']}: block {block.date()}..{block_end.date()} "
                f"train={len(train):,} test={len(test):,}")
        block = block_end + pd.Timedelta(days=1)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summarize(preds):
    """MAPE (%) for the model and each baseline, plus per-product wins against naive."""
    if preds.empty:
        return {}
    errs = {name: ape(preds[name], preds["y"]) for name in ["model", *BASELINES]}
    summary = {f"mape_{k}": float(np.mean(v) * 100) for k, v in errs.items()}
    per_product = pd.DataFrame({"product_id": preds["product_id"], "model": errs["model"],
                                "naive": errs["naive"]}).groupby("product_id").mean()
    summary["products"] = int(len(per_product))
    summary["products_beating_naive"] = int((per_product["model"] < per_product["naive"]).sum())
    summary["rows"] = int(len(preds))
    for h in (1, 7):
        sel = preds["h"] == h
        summary[f"mape_model_h{h}"] = float(np.mean(errs["model"][sel]) * 100)
        summary[f"mape_naive_h{h}"] = float(np.mean(errs["naive"][sel]) * 100)
    return summary


def per_product_table(preds, products):
    errs = pd.DataFrame({"product_id": preds["product_id"],
                         "model": ape(preds["model"], preds["y"]) * 100,
                         "naive": ape(preds["naive"], preds["y"]) * 100})
    t = errs.groupby("product_id").mean()
    t["model_better"] = t["model"] < t["naive"]
    t["name_en"] = [products[p]["name_en"] for p in t.index]
    return t.sort_values("naive", ascending=False)
