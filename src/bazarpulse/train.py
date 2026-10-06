"""Train, compare and register forecasting models.

    python -m bazarpulse.train --initial   # 26-week backtest of every candidate; register the best
    python -m bazarpulse.train --weekly    # 8-week challenger vs champion; switch only if clearly better

Whatever config wins is refit on all data and registered as a new champion version;
the old one is kept as the rollback target.
"""
import argparse
import json
import os

import pandas as pd

from bazarpulse import catalog, features, models, registry, tracking
from bazarpulse.build import PRICES

REPORTS = "reports"
PROMOTE_MARGIN = 0.02


def load_rows():
    products = catalog.load_products()
    prices = pd.read_parquet(PRICES)
    prices = prices[prices["product_id"].isin(products)]
    return prices, products, features.training_rows(prices, products)


def evaluate(rows, configs, weeks, log):
    end = rows["date"].max()
    start = end - pd.Timedelta(weeks=weeks) + pd.Timedelta(days=1)
    results = {}
    for cfg in configs:
        log(f"  backtesting {cfg['name']} on origins {start.date()} .. {end.date()}")
        with tracking.run(f"backtest-{cfg['name']}-{weeks}w", params={**cfg, "weeks": weeks}, log=log) as ml:
            preds = models.backtest(rows, cfg, start, end, log=log)
            summary = models.summarize(preds)
            tracking.log_metrics(ml, summary)
        results[cfg["name"]] = {"summary": summary, "preds": preds}
    return results, start, end


def _fit_and_register(rows, config, summary, decision, log):
    log(f"  refitting {config['name']} on all {len(rows):,} rows")
    with tracking.run(f"train-{config['name']}", params=config, log=log) as ml:
        booster = models.fit(rows, config)
        entry = registry.register(booster, config, rows["target_date"].max().date(), summary, decision)
        tracking.log_metrics(ml, summary, prefix="backtest_")
        tracking.log_artifact(ml, entry["file"])
    log(f"  registered champion v{entry['version']} ({config['name']})")
    return entry


def write_report(results, start, end, products, best):
    os.makedirs(REPORTS, exist_ok=True)
    lines = ["# Backtest report\n", f"Origins {start.date()} to {end.date()}, horizons 1-7 days, "
             "models refit every 28 days on data known before each block.\n",
             "| Model | MAPE all h | MAPE h=1 | MAPE h=7 | Products beating naive |", "|---|---|---|---|---|"]
    any_summary = next(iter(results.values()))["summary"]
    for name in ("naive", "drift", "ma7"):
        lines.append(f"| baseline: {name} | {any_summary[f'mape_{name}']:.2f}% | | | |")
    for name, r in results.items():
        s = r["summary"]
        lines.append(f"| {name} | {s['mape_model']:.2f}% | {s['mape_model_h1']:.2f}% | "
                     f"{s['mape_model_h7']:.2f}% | {s['products_beating_naive']} of {s['products']} |")
    table = models.per_product_table(results[best]["preds"], products)
    lines += [f"\n## Per product ({best}), most volatile first\n",
              "| Product | Model MAPE | Naive MAPE | Model better |", "|---|---|---|---|"]
    for _, r in table.iterrows():
        better = "yes" if r["model_better"] else "no"
        lines.append(f"| {r['name_en']} | {r['model']:.2f}% | {r['naive']:.2f}% | {better} |")
    with open(os.path.join(REPORTS, "backtest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(REPORTS, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump({n: r["summary"] for n, r in results.items()}, f, indent=2)


def initial(log=print):
    _, products, rows = load_rows()
    log(f"training rows: {len(rows):,}")
    results, start, end = evaluate(rows, models.CANDIDATES, weeks=26, log=log)
    best = min(results, key=lambda n: results[n]["summary"]["mape_model"])
    write_report(results, start, end, products, best)
    s = results[best]["summary"]
    config = next(c for c in models.CANDIDATES if c["name"] == best)
    beats = s["mape_model"] < s["mape_naive"]
    log(f"best: {best} MAPE {s['mape_model']:.2f}% vs naive {s['mape_naive']:.2f}% "
        f"({'beats' if beats else 'DOES NOT beat'} naive)")
    return _fit_and_register(rows, config, s, {
        "kind": "initial", "promoted": True, "beats_naive": beats,
        "scores": {n: round(r["summary"]["mape_model"], 3) for n, r in results.items()},
        "reason": f"best of {len(results)} candidates on a 26-week backtest"}, log)


def weekly(log=print):
    reg = registry.load()
    if not reg["champion"]:
        return initial(log)
    _, products, rows = load_rows()
    latest = str(rows["target_date"].max().date())
    if latest == reg["champion"]["trained_until"]:
        registry.log_decision({"kind": "weekly", "promoted": False,
                               "reason": "no new data since last training"})
        log("no new data since the champion was trained; nothing to do")
        return reg["champion"]

    results, _, _ = evaluate(rows, models.CANDIDATES, weeks=8, log=log)
    champ_name = reg["champion"]["config"]["name"]
    champ = results[champ_name]["summary"]
    best = min(results, key=lambda n: results[n]["summary"]["mape_model"])
    b = results[best]["summary"]
    switch = (best != champ_name and b["mape_model"] < champ["mape_model"] * (1 - PROMOTE_MARGIN)
              and b["mape_model"] < b["mape_naive"])
    chosen = best if switch else champ_name
    reason = (f"{best} beat {champ_name} ({b['mape_model']:.2f}% vs {champ['mape_model']:.2f}%)" if switch
              else f"kept {champ_name}: best challenger {best} at {b['mape_model']:.2f}% vs champion "
                   f"{champ['mape_model']:.2f}% (needs >= {PROMOTE_MARGIN:.0%} improvement)")
    log(reason)
    config = next(c for c in models.CANDIDATES if c["name"] == chosen)
    return _fit_and_register(rows, config, results[chosen]["summary"], {
        "kind": "weekly", "promoted": switch, "config_changed": switch,
        "scores": {n: round(r["summary"]["mape_model"], 3) for n, r in results.items()},
        "naive": round(champ["mape_naive"], 3), "reason": reason}, log)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--initial", action="store_true")
    g.add_argument("--weekly", action="store_true")
    args = ap.parse_args()
    log = lambda m: print(m, flush=True)  # noqa: E731
    initial(log) if args.initial else weekly(log)


if __name__ == "__main__":
    main()
