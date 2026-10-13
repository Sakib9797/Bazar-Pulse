"""Daily pipeline: fetch -> parse -> validate -> score past forecasts -> forecast.

    python -m bazarpulse.pipeline

Exits with code 1 on a hard failure. In GitHub Actions that fails the run (GitHub
emails the owner) and skips the commit step, so bad data is never published and
the last good forecast stays live.
"""
import json
import os
from datetime import UTC, datetime

import pandas as pd

from bazarpulse import alerts, build, catalog, ingest, monitor, predict, registry, validate

STATUS = os.path.join("data", "status.json")


def run(log=print):
    try:
        new_files, failures = ingest.sync(log=log)
    except Exception as e:
        alerts.send(f"Could not read TCB's price list: {type(e).__name__}: {e}", "error")
        return 1
    if failures:
        alerts.send(f"{len(failures)} file download(s) failed, e.g. {failures[0][1]}", "warning")
    if not new_files:
        log("no new TCB files; nothing to do")
        return 0

    result = build.build(log=log)
    rep = result["new_files"]
    bad = rep[rep["status"] == "failed"]
    if len(bad):
        alerts.send(f"{len(bad)} new file(s) could not be parsed: {bad['error'].iloc[0]}", "warning")
    new_days = set(pd.to_datetime(rep.loc[rep["status"] == "ok", "report_date"]))
    if not new_days:
        alerts.send("New TCB file(s) arrived but none could be parsed. Nothing published.", "error")
        return 1

    products = catalog.load_products()
    prices = result["prices"]
    hard, warn = validate.check_days(prices, pd.read_parquet(build.OBS), new_days, products.keys())
    unmapped = result["unmapped"]
    if len(unmapped):
        fresh = unmapped[pd.to_datetime(unmapped["last_seen"]).isin(new_days)]
        if len(fresh):
            warn.append(f"{len(fresh)} product spelling(s) not in the catalog, e.g. "
                        f"'{fresh['name_key'].iloc[0]}' ({fresh['unit_key'].iloc[0]})")
    for w in warn:
        alerts.send(w, "warning")
    if hard:
        for h in hard:
            alerts.send(h, "error")
        return 1
    return publish(prices, log)


def publish(prices, log=print):
    """Score past forecasts, check health and drift, forecast, and write status.json."""
    monitor.score(log)
    health = monitor.health(log)
    previous = {}
    if os.path.exists(monitor.DRIFT):
        with open(monitor.DRIFT, encoding="utf-8") as f:
            previous = json.load(f)
    drift = monitor.drift(log)
    newly = sorted(set(drift["drifted"]) - set(previous.get("drifted", [])))
    if newly:
        alerts.send(f"Unusual price behaviour this month (drift above the category's normal range) in: "
                    f"{', '.join(newly)}", "warning")

    predict.run(log=log)
    champ = registry.load()["champion"]
    last_day = prices["date"].max()
    status = {
        "last_data_date": f"{last_day:%Y-%m-%d}",
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "products_today": int((prices["date"] == last_day).sum()),
        "price_rows": int(len(prices)),
        "model_version": champ["version"], "model": champ["config"]["name"],
        "health": (health or {}).get("status", "warming_up"),
    }
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    log(f"done: {status}")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Bazar Pulse daily pipeline")
    ap.add_argument("--refresh", action="store_true",
                    help="skip fetching; re-score, re-forecast and rewrite status from data on disk")
    log = lambda m: print(m, flush=True)  # noqa: E731
    if ap.parse_args().refresh:
        raise SystemExit(publish(pd.read_parquet(build.PRICES), log))
    raise SystemExit(run(log=log))


if __name__ == "__main__":
    main()
