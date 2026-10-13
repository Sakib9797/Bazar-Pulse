"""Data contract for the clean price table, plus day-level checks.

HARD failures stop the daily pipeline (nothing is published, the last good forecast
stays up). WARNINGS are alerted but the run continues.

    python -m bazarpulse.validate      # full-history data quality report -> reports/data_quality.md
"""
import os

import pandas as pd
import pandera.pandas as pa

from bazarpulse import catalog
from bazarpulse.build import OBS, PRICES, REPORT

MIN_PRODUCTS_PER_DAY = 40
JUMP_WARN = 0.5          # day-over-day change that is suspicious enough to flag
CROSSCHECK_WARN = 0.2    # share of "1 week ago" prices that disagree with what we stored


def price_schema(product_ids):
    price = pa.Column(float, [pa.Check.gt(0), pa.Check.lt(1_000_000)], coerce=True)
    return pa.DataFrameSchema(
        {"date": pa.Column("datetime64[ns]", pa.Check.le(pd.Timestamp.now() + pd.Timedelta(days=1)),
                           coerce=True),
         "product_id": pa.Column(str, pa.Check.isin(sorted(product_ids)), coerce=True),
         "price_min": price, "price_max": price, "price_mid": price},
        checks=pa.Check(lambda d: d["price_min"] <= d["price_max"], error="price_min > price_max"),
        unique=["date", "product_id"], strict=False)


def check_days(prices, obs, days, product_ids):
    """Validate the given report dates. Returns (hard_errors, warnings)."""
    hard, warn = [], []
    try:
        price_schema(product_ids).validate(prices, lazy=True)
    except pa.errors.SchemaErrors as e:
        hard.append(f"price table violates its schema: {len(e.failure_cases)} failing value(s)")

    prices = prices.sort_values("date")
    for day in sorted(pd.to_datetime(pd.Series(list(days))).unique()):
        today = prices[prices["date"] == day]
        if len(today) < MIN_PRODUCTS_PER_DAY:
            hard.append(f"{day.date()}: only {len(today)} products (expected >= {MIN_PRODUCTS_PER_DAY})")
            continue
        before = prices[prices["date"] < day].groupby("product_id").last()
        joined = today.set_index("product_id").join(before["price_mid"].rename("prev"), how="inner")
        jumps = joined[(joined["price_mid"] / joined["prev"] - 1).abs() > JUMP_WARN]
        if len(jumps):
            warn.append(f"{day.date()}: {len(jumps)} price(s) moved >{JUMP_WARN:.0%} in one step: "
                        + ", ".join(jumps.index[:5]))
        mism = crosscheck(prices, obs, day)
        if mism is not None and mism > CROSSCHECK_WARN:
            warn.append(f"{day.date()}: {mism:.0%} of this file's '1 week ago' prices disagree "
                        "with the prices stored for that date")
    return hard, warn


def crosscheck(prices, obs, day):
    """Share of products whose 'one week ago' price in today's file differs from what we stored."""
    if obs is None or obs.empty:
        return None
    o = obs[pd.to_datetime(obs["report_date"]) == day]
    if o.empty:
        return None
    aliases = catalog.load_aliases()
    ids = [catalog.lookup(aliases, n, u) for n, u in zip(o["product_raw"], o["unit_raw"], strict=True)]
    o = o.assign(product_id=ids)
    o = o.dropna(subset=["product_id", "week_min"])
    stored = prices[prices["date"] == day - pd.Timedelta(days=7)].set_index("product_id")["price_min"]
    both = o.join(stored.rename("stored_min"), on="product_id", how="inner")
    if len(both) < 10:
        return None
    return float((both["week_min"] - both["stored_min"]).abs().gt(0.5).mean())


def quality_report():
    prices = pd.read_parquet(PRICES)
    obs = pd.read_parquet(OBS)
    rep = pd.read_csv(REPORT, dtype=str, keep_default_na=False)
    product_ids = catalog.load_products().keys()
    hard, _ = check_days(prices, None, [], product_ids)
    failed = rep[rep["status"] == "failed"]
    header_warn = rep[rep["warnings"].str.contains("repeated header", na=False)]
    days = prices.groupby("date")["product_id"].nunique()
    sample = sorted(prices["date"].unique())[-120::7]
    rates = [r for r in (crosscheck(prices, obs, pd.Timestamp(d)) for d in sample) if r is not None]
    lines = [
        "# Data quality report\n",
        f"- Files downloaded: **{len(rep)}**; parsed OK: **{(rep['status'] == 'ok').sum()}**; "
        f"failed: **{len(failed)}**",
        f"- Price rows: **{len(prices):,}** for **{prices['product_id'].nunique()}** products, "
        f"{prices['date'].min().date()} to {prices['date'].max().date()} ({len(days)} report days)",
        f"- Products per report day: median {int(days.median())}, min {int(days.min())}",
        f"- Files whose repeated page header carries a different date: **{len(header_warn)}**",
        f"- Schema check on the full table: **{'pass' if not hard else '; '.join(hard)}**",
        f"- '1 week ago' cross-check (sampled weekly, last ~4 months): median mismatch "
        f"{(pd.Series(rates).median() * 100 if rates else float('nan')):.1f}% of products",
        "\n## Files that failed to parse\n",
    ]
    lines += [f"- `{r['path']}`: {r['error']}" for _, r in failed.iterrows()] or ["- none"]
    report_days = pd.Series(sorted(prices["date"].unique()))
    per_year = report_days.dt.year.value_counts().sort_index()
    gaps = report_days.diff().dt.days
    lines += ["\n## Coverage\n", "| Year | Report days |", "|---|---|"]
    lines += [f"| {y} | {n} |" for y, n in per_year.items()]
    lines += ["\nLargest gaps between report days (TCB's archive has no files for these periods):\n"]
    for i in gaps.nlargest(3).index:
        lines.append(f"- {report_days[i - 1].date()} to {report_days[i].date()}: {int(gaps[i])} days")
    os.makedirs("reports", exist_ok=True)
    with open(os.path.join("reports", "data_quality.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    quality_report()
