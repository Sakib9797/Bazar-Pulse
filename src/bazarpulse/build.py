"""Parse downloaded files into clean datasets.

    data/clean/observations.parquet  every parsed row, raw names kept (audit trail)
    data/clean/parse_report.csv      one line per file: ok / failed, why, warnings
    data/clean/prices.parquet        one row per (product_id, date): min, max, mid
    data/clean/unmapped.csv          raw spellings not yet in catalog/aliases.csv

Parsing is incremental: a file already in parse_report.csv is not parsed again
unless --rebuild is given. prices.parquet is re-derived from observations every
time, so catalog edits apply to the whole history.

    python -m bazarpulse.build [--rebuild]
"""
import argparse
import os

import pandas as pd

from bazarpulse import catalog
from bazarpulse.ingest import load_manifest
from bazarpulse.parse import ParseError, parse_workbook

CLEAN = os.path.join("data", "clean")
OBS = os.path.join(CLEAN, "observations.parquet")
REPORT = os.path.join(CLEAN, "parse_report.csv")
PRICES = os.path.join(CLEAN, "prices.parquet")
UNMAPPED = os.path.join(CLEAN, "unmapped.csv")
PRICE_COLS = [f"{b}_{m}" for b in ("today", "week", "month", "year") for m in ("min", "max")]


def parse_files(entries):
    obs, report = [], []
    for e in entries:
        line = {"path": e["path"], "listing_date": e["listing_date"] or None, "status": "ok",
                "report_date": None, "rows": 0, "error": "", "warnings": ""}
        try:
            out = parse_workbook(e["path"])
        except ParseError as ex:
            line.update(status="failed", error=str(ex))
        else:
            line.update(report_date=out["report_date"].isoformat(), rows=len(out["rows"]),
                        warnings=" | ".join(out["warnings"]))
            for r in out["rows"]:
                obs.append({**r, "source_file": e["path"], "listing_date": e["listing_date"] or None})
        report.append(line)
    return pd.DataFrame(obs), pd.DataFrame(report)


def derive_prices(obs, aliases):
    """Map observations to product ids and keep one row per product per day."""
    if obs.empty:
        return pd.DataFrame(columns=["date", "product_id", "price_min", "price_max", "price_mid",
                                     "source_file"]), pd.DataFrame()
    df = obs.copy()
    df["name_key"] = df["product_raw"].map(catalog.key)
    df["unit_key"] = df["unit_raw"].map(catalog.key)
    df["product_id"] = [aliases.get((n, u)) for n, u in zip(df["name_key"], df["unit_key"], strict=True)]

    unmapped = (df[df["product_id"].isna()]
                .groupby(["name_key", "unit_key", "section"], dropna=False)
                .agg(first_seen=("report_date", "min"), last_seen=("report_date", "max"),
                     files=("source_file", "nunique"))
                .reset_index().sort_values("files", ascending=False))

    df = df[df["product_id"].notna()].copy()
    df["price_min"] = df["today_min"].fillna(df["today_max"])
    df["price_max"] = df["today_max"].fillna(df["today_min"])
    df = df[df["price_min"].notna()]
    df["price_mid"] = (df["price_min"] + df["price_max"]) / 2
    df["date"] = pd.to_datetime(df["report_date"])
    # Two files can carry the same report date (re-uploads). Keep the most complete one;
    # identical duplicates collapse to a single row.
    df["completeness"] = df.groupby("source_file")["price_mid"].transform("count")
    df = (df.sort_values(["date", "product_id", "completeness"], ascending=[True, True, False])
            .drop_duplicates(["date", "product_id"]))
    cols = ["date", "product_id", "price_min", "price_max", "price_mid", "source_file"]
    return df[cols].reset_index(drop=True), unmapped


def build(rebuild=False, log=print):
    os.makedirs(CLEAN, exist_ok=True)
    manifest = [m for m in load_manifest().values() if m["path"].endswith((".xlsx", ".xlsm"))]
    old_obs = pd.read_parquet(OBS) if os.path.exists(OBS) and not rebuild else pd.DataFrame()
    old_rep = pd.read_csv(REPORT, dtype=str, keep_default_na=False) \
        if os.path.exists(REPORT) and not rebuild else pd.DataFrame()

    done = set(old_rep["path"]) if not old_rep.empty else set()
    todo = [m for m in manifest if m["path"] not in done]
    log(f"parsing {len(todo)} new file(s) ({len(done)} already parsed)")
    new_obs, new_rep = parse_files(todo)

    obs = pd.concat([old_obs, new_obs], ignore_index=True) if not new_obs.empty else old_obs
    rep = pd.concat([old_rep, new_rep.astype(str)], ignore_index=True) if not new_rep.empty else old_rep
    if not obs.empty:
        obs["report_date"] = pd.to_datetime(obs["report_date"]).dt.date
        obs.to_parquet(OBS, index=False)
    rep.sort_values("path").to_csv(REPORT, index=False)

    prices, unmapped = derive_prices(obs, catalog.load_aliases())
    prices.to_parquet(PRICES, index=False)
    unmapped.to_csv(UNMAPPED, index=False)

    failed = int((rep["status"] == "failed").sum()) if not rep.empty else 0
    log(f"files: {len(rep)} parsed, {failed} failed | observations: {len(obs)} | "
        f"prices: {len(prices)} rows, {prices['product_id'].nunique() if len(prices) else 0} products "
        f"| unmapped spellings: {len(unmapped)}")
    return {"new_files": new_rep, "prices": prices, "unmapped": unmapped}


def main():
    ap = argparse.ArgumentParser(description="Parse raw files into clean datasets")
    ap.add_argument("--rebuild", action="store_true", help="re-parse every file")
    build(rebuild=ap.parse_args().rebuild, log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
