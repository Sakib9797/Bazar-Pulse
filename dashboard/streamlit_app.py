"""Bazar Pulse dashboard (Streamlit Community Cloud entry point)."""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@st.cache_data(ttl=600)
def load():
    latest = read_json(DATA / "forecasts" / "latest.json")
    prices = pd.read_parquet(DATA / "clean" / "prices.parquet")
    daily_path = DATA / "monitoring" / "daily_metrics.parquet"
    daily = pd.read_parquet(daily_path) if daily_path.exists() else pd.DataFrame()
    return (latest, prices, daily, read_json(DATA / "status.json"),
            read_json(DATA / "monitoring" / "health.json"), read_json(ROOT / "models" / "registry.json"),
            read_json(ROOT / "reports" / "backtest.json"),
            read_json(ROOT / "reports" / "backtest_products.json") or {})


st.set_page_config(page_title="Bazar Pulse | বাজারদর পূর্বাভাস", page_icon="🛒", layout="wide")
latest, prices, daily, status, health, registry, backtest, product_bt = load()

st.title("🛒 Bazar Pulse")
st.caption("Where Dhaka's essential-goods prices are likely to be in 1-4 weeks · "
           "ঢাকার নিত্যপণ্যের দাম আগামী ১-৪ সপ্তাহে কোথায় থাকতে পারে")
if not latest:
    st.error("No forecast has been produced yet.")
    st.stop()

products = {p["product_id"]: p for p in latest["products"]}
cover = int(latest.get("coverage_target", 0.8) * 100)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest TCB data", latest["origin_date"])
c2.metric("Products tracked", len(products))
c3.metric("Champion model", f"v{latest['model_version']} · {latest['model']}")
c4.metric("Model health", (health or {}).get("status", "warming_up").replace("_", " "))
st.info(f"Each forecast is a **likely range**: the real price should land inside it about {cover}% of the "
        "time. Source: Trading Corporation of Bangladesh (TCB) daily retail price sheets for Dhaka. "
        "Estimates for information only, not official prices.", icon="ℹ️")

tab_movers, tab_explore, tab_health = st.tabs(["📈 Next 4 weeks", "🔎 Explore a product", "🩺 Model health"])

with tab_movers:
    rows = []
    for p in products.values():
        f = p["forecast"][-1]
        rows.append({"Product": f"{p['name_en']} ({p['name_bn']})", "Unit": p["unit"],
                     "Today (৳)": p["last_price"], "Likely in 4 weeks (৳)": f["mid"],
                     "Range (৳)": f"{f['low']:,.0f} – {f['high']:,.0f}",
                     "Likely change %": f["change_pct"], "Upside risk %": f["upside_pct"]})
    table = pd.DataFrame(rows)
    left, right = st.columns(2)
    left.subheader("Highest upside risk")
    left.caption("Largest rise at the top of the likely range")
    left.dataframe(table.sort_values("Upside risk %", ascending=False).head(10), hide_index=True,
                   width="stretch")
    right.subheader("Largest likely change")
    right.caption("Middle of the range vs today")
    right.dataframe(table.reindex(table["Likely change %"].abs().sort_values(ascending=False).index).head(10),
                    hide_index=True, width="stretch")

with tab_explore:
    by_label = {f"{p['name_en']} · {p['name_bn']} ({p['unit']})": pid
                for pid, p in sorted(products.items(), key=lambda kv: kv[1]["name_en"])}
    choice = st.selectbox("Product", list(by_label))
    days = st.select_slider("History", options=[90, 180, 365, 730, 1825], value=180,
                            format_func=lambda d: f"{d} days")
    pid = by_label[choice]
    p = products[pid]
    hist = prices[prices["product_id"] == pid]
    hist = hist[hist["date"] > hist["date"].max() - pd.Timedelta(days=days)]
    start = {"date": latest["origin_date"], **dict.fromkeys(("low", "mid", "high"), p["last_price"])}
    fc = pd.DataFrame([start] + p["forecast"]).assign(date=lambda d: pd.to_datetime(d["date"]))
    band = alt.Chart(hist).mark_area(opacity=0.2).encode(
        x=alt.X("date:T", title=None), y=alt.Y("price_min:Q", title="Price (৳)"), y2="price_max:Q")
    line = alt.Chart(hist).mark_line().encode(x="date:T", y="price_mid:Q",
                                              tooltip=["date:T", "price_min", "price_max"])
    fband = alt.Chart(fc).mark_area(opacity=0.25, color="#d62728").encode(x="date:T", y="low:Q", y2="high:Q")
    fmid = alt.Chart(fc).mark_line(strokeDash=[4, 3], point=True, color="#d62728").encode(
        x="date:T", y="mid:Q", tooltip=["date:T", "low", "mid", "high"])
    st.altair_chart(band + line + fband + fmid, use_container_width=True)
    st.caption("Blue: TCB's lowest-highest price each day and the midpoint. "
               f"Red: likely price and {cover}% range for the next 1-4 weeks.")
    bt = product_bt.get(pid)
    if bt:
        msg = (f"In the 26-week backtest, this product's range contained the real price "
               f"**{bt['coverage']:.0%}** of the time (target {cover}%).")
        if bt["coverage"] < 0.65:
            st.warning(msg + " Prices of this item swing more than the model expects; treat the range "
                       "as optimistic.", icon="⚠️")
        else:
            st.caption(msg)
    st.dataframe(pd.DataFrame(p["forecast"]).rename(columns={
        "date": "Date", "weeks": "Weeks ahead", "low": "Low (৳)", "mid": "Likely (৳)", "high": "High (৳)",
        "change_pct": "Likely change %", "upside_pct": "Upside risk %"}), hide_index=True)

with tab_health:
    if health and health.get("live_coverage") is not None:
        h1, h2, h3 = st.columns(3)
        h1.metric("Live range coverage (28 days)", f"{health['live_coverage']:.0%}", f"target {cover}%",
                  delta_color="off")
        h2.metric("Live pinball loss: model", f"{health['live_pinball']:.3f}")
        h3.metric("Live pinball loss: baseline", f"{health['live_pinball_climatology']:.3f}")
    else:
        st.write("Live accuracy appears once forecasts start reaching their dates "
                 f"({(health or {}).get('live_rows', 0)} checked so far). "
                 "The first ones mature after a week.")
    if not daily.empty:
        d = daily.melt(id_vars="target_date", value_vars=["coverage", "coverage_climatology"],
                       var_name="series", value_name="share inside range")
        st.altair_chart(alt.Chart(d).mark_line(point=True).encode(
            x=alt.X("target_date:T", title=None), y=alt.Y("share inside range:Q", axis=alt.Axis(format="%")),
            color="series:N"), use_container_width=True)
    if backtest:
        st.subheader("Backtest before launch (26 weeks)")
        st.caption("Pinball loss: lower is better. Skill: improvement over each product's own typical range "
                   "of changes in the previous year (climatology).")
        bt = pd.DataFrame(backtest).T[["pinball_model", "pinball_climatology", "skill", "coverage_model",
                                       "width_model", "products_beating_climatology", "products"]]
        st.dataframe(bt.style.format({"pinball_model": "{:.4f}", "pinball_climatology": "{:.4f}",
                                      "skill": "{:+.1%}", "coverage_model": "{:.1%}",
                                      "width_model": "{:.2f}%"}))
    if registry:
        st.subheader("Model decisions")
        st.dataframe(pd.DataFrame(registry["decisions"]).iloc[::-1], hide_index=True, width="stretch")
    if status:
        st.caption(f"Pipeline last updated {status['updated_at']} UTC · {status['price_rows']:,} price rows.")
