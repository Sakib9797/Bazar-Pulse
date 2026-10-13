"""Train, compare and register range-forecast models.

    python -m bazarpulse.train --initial   # 26-week backtest of every candidate; register the best
    python -m bazarpulse.train --weekly    # 8-week challenger vs champion; switch only if clearly better

The score is the pinball loss of the low / likely / high forecasts (lower is better).
A model must beat the climatology baseline to be served; if none does, the baseline
itself is registered as champion. Whatever wins is refit on the latest data and stored
as a new champion version; the old one is kept as the rollback target.
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
    return products, features.training_rows(prices, products)


def evaluate(rows, configs, weeks, log):
    end = rows["date"].max()
    start = end - pd.Timedelta(weeks=weeks) + pd.Timedelta(days=1)
    results = {}
    for cfg in configs:
        log(f"  backtesting {cfg['name']} on origins {start.date()} .. {end.date()}")
        with tracking.run(f"backtest-{cfg['name']}-{weeks}w", params={**cfg, "weeks": weeks}, log=log) as ml:
            res = models.backtest(rows, cfg, start, end, log=log)
            summary = models.summarize(res)
            tracking.log_metrics(ml, summary)
        log(f"    pinball {summary['pinball_model']:.4f} (climatology {summary['pinball_climatology']:.4f}, "
            f"skill {summary['skill']:+.1%}), coverage {summary['coverage_model']:.1%}")
        results[cfg["name"]] = {"summary": summary, "res": res}
    return results, start, end


def _choose(results):
    """Best candidate by pinball loss, or the climatology baseline if no model beats it."""
    best = min(results, key=lambda n: results[n]["summary"]["pinball_model"])
    s = results[best]["summary"]
    if s["pinball_model"] >= s["pinball_climatology"]:
        return models.CLIMATOLOGY, s
    return next(c for c in models.CANDIDATES if c["name"] == best), s


def _fit_and_register(rows, config, summary, decision, log):
    with tracking.run(f"train-{config['name']}", params=config, log=log) as ml:
        model = None
        if config["name"] != models.CLIMATOLOGY["name"]:
            log(f"  fitting {config['name']} on {len(rows):,} rows "
                f"(last {models.CAL_DAYS} days for calibration)")
            model = models.fit(rows, config)
        entry = registry.register(model, config, rows["target_date"].max().date(), summary, decision)
        tracking.log_metrics(ml, summary, prefix="backtest_")
        if entry["file"]:
            tracking.log_artifact(ml, entry["file"])
    log(f"  registered champion v{entry['version']} ({config['name']})")
    return entry


def write_report(results, start, end, products, chosen):
    os.makedirs(REPORTS, exist_ok=True)
    any_s = next(iter(results.values()))["summary"]
    lines = [
        "# Backtest report\n",
        f"Forecast origins {start.date()} to {end.date()}; horizons 1, 2, 3 and 4 weeks; models refit every "
        f"28 days using only data known before each block (last {models.CAL_DAYS} days held out for "
        "calibration).\n",
        "Score = pinball loss of the 10% / 50% / 90% forecasts (lower is better). Skill = improvement over "
        "**climatology**: each product's own range of price changes over the previous year.\n",
        "| Model | Pinball | Skill vs climatology | 80% range covers | Range width | Products better |",
        "|---|---|---|---|---|---|",
        f"| baseline: climatology | {any_s['pinball_climatology']:.4f} | - | "
        f"{any_s['coverage_climatology']:.1%} | {any_s['width_climatology']:.2f}% | - |",
    ]
    for name, r in results.items():
        s = r["summary"]
        lines.append(f"| {name} | {s['pinball_model']:.4f} | {s['skill']:+.1%} | {s['coverage_model']:.1%} | "
                     f"{s['width_model']:.2f}% | {s['products_beating_climatology']} of {s['products']} |")
    best = min(results, key=lambda n: results[n]["summary"]["pinball_model"])
    s = results[best]["summary"]
    lines += ["\n## By horizon (" + best + ")\n", "| Horizon | Skill | 80% range covers |", "|---|---|---|"]
    for h in features.HORIZONS:
        weeks = f"{h // 7} week{'s' if h > 7 else ''}"
        lines.append(f"| {weeks} | {s[f'skill_h{h}']:+.1%} | {s[f'coverage_h{h}']:.1%} |")
    lines += [
        "\n## Exact-price forecasts\n",
        f"The median forecast's error is {s['mape_mid']:.2f}% vs {s['mape_naive']:.2f}% "
        "for \"price stays the same\". Most TCB prices do not move in a given week, so exact forecasts "
        "do not beat no-change; "
        "the useful, measurable signal is in the range.\n",
        f"Champion chosen: **{chosen}**.\n",
        f"\n## Per product ({best}), most volatile first\n",
        "| Product | Model pinball | Climatology | Range covers | Better |", "|---|---|---|---|---|"]
    table = models.per_product_table(results[best]["res"], products)
    for _, r in table.iterrows():
        lines.append(f"| {r['name_en']} | {r['model']:.3f} | {r['climatology']:.3f} | {r['covered']:.0%} | "
                     f"{'yes' if r['model_better'] else 'no'} |")
    with open(os.path.join(REPORTS, "backtest_products.json"), "w", encoding="utf-8") as f:
        json.dump({pid: {"coverage": round(float(r["covered"]), 3), "model_better": bool(r["model_better"])}
                   for pid, r in table.iterrows()}, f, indent=1)
    with open(os.path.join(REPORTS, "backtest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(REPORTS, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump({n: r["summary"] for n, r in results.items()}, f, indent=2)


def initial(log=print):
    products, rows = load_rows()
    log(f"training rows: {len(rows):,}")
    results, start, end = evaluate(rows, models.CANDIDATES, weeks=26, log=log)
    config, s = _choose(results)
    write_report(results, start, end, products, config["name"])
    log(f"chosen: {config['name']}")
    return _fit_and_register(rows, config, s, {
        "kind": "initial", "promoted": True, "beats_climatology": config["name"] != "climatology",
        "scores": {n: round(r["summary"]["pinball_model"], 4) for n, r in results.items()},
        "climatology": round(s["pinball_climatology"], 4),
        "reason": f"best of {len(results)} candidates on a 26-week backtest"}, log)


def weekly(log=print):
    reg = registry.load()
    if not reg["champion"]:
        return initial(log)
    _, rows = load_rows()
    if str(rows["target_date"].max().date()) == reg["champion"]["trained_until"]:
        registry.log_decision({"kind": "weekly", "promoted": False,
                               "reason": "no new data since last training"})
        log("no new data since the champion was trained; nothing to do")
        return reg["champion"]

    results, _, _ = evaluate(rows, models.CANDIDATES, weeks=8, log=log)
    champ_name = reg["champion"]["config"]["name"]
    best_cfg, best = _choose(results)
    champ = results[champ_name]["summary"] if champ_name in results else None
    champ_score = champ["pinball_model"] if champ else best["pinball_climatology"]
    new_score = best["pinball_model"] if best_cfg["name"] in results else best["pinball_climatology"]
    switch = best_cfg["name"] != champ_name and new_score < champ_score * (1 - PROMOTE_MARGIN)
    chosen = best_cfg if switch else reg["champion"]["config"]
    reason = (f"{best_cfg['name']} beat {champ_name} ({new_score:.4f} vs {champ_score:.4f})" if switch
              else f"kept {champ_name} ({champ_score:.4f}); best challenger {best_cfg['name']} at "
                   f"{new_score:.4f} (needs >= {PROMOTE_MARGIN:.0%} improvement)")
    log(reason)
    summary = results[chosen["name"]]["summary"] if chosen["name"] in results else best
    return _fit_and_register(rows, chosen, summary, {
        "kind": "weekly", "promoted": switch,
        "scores": {n: round(r["summary"]["pinball_model"], 4) for n, r in results.items()},
        "climatology": round(best["pinball_climatology"], 4), "reason": reason}, log)


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
