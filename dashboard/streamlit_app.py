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
            read_json(ROOT / "reports" / "backtest.json"))


st.set_page_config(page_title="Bazar Pulse | বাজারদর পূর্বাভাস", page_icon="🛒", layout="wide")
latest, prices, daily, status, health, registry, backtest = load()

st.title("🛒 Bazar Pulse")
st.caption("7-day price forecasts for Dhaka's essential goods · ঢাকার নিত্যপণ্যের ৭ দিনের দামের পূর্বাভাস")
if not latest:
    st.error("No forecast has been produced yet.")
    st.stop()

products = {p["product_id"]: p for p in latest["products"]}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest TCB data", latest["origin_date"])
c2.metric("Products tracked", len(products))
c3.metric("Model", f"v{latest['model_version']} · {latest['model']}")
c4.metric("Model health", (health or {}).get("status", "warming_up").replace("_", " "))
st.info("Source: Trading Corporation of Bangladesh (TCB) daily retail price sheets for Dhaka. "
        "Forecasts are estimates for information only, not official prices.", icon="ℹ️")

tab_movers, tab_explore, tab_health = st.tabs(["📈 Biggest expected moves", "🔎 Explore a product",
                                               "🩺 Model health"])

with tab_movers:
    rows = [{"Product": f"{p['name_en']} ({p['name_bn']})", "Unit": p["unit"],
             "Today (৳)": p["last_price"], "In 7 days (৳)": p["forecast"][-1]["price"],
             "Change %": p["forecast"][-1]["change_pct"]} for p in products.values()]
    movers = pd.DataFrame(rows).sort_values("Change %")
    left, right = st.columns(2)
    left.subheader("Expected to rise")
    left.dataframe(movers.iloc[::-1].head(10), hide_index=True, width="stretch")
    right.subheader("Expected to fall")
    right.dataframe(movers.head(10), hide_index=True, width="stretch")

with tab_explore:
    by_label = {f"{p['name_en']} · {p['name_bn']} ({p['unit']})": pid
                for pid, p in sorted(products.items(), key=lambda kv: kv[1]["name_en"])}
    choice = st.selectbox("Product", list(by_label))
    days = st.select_slider("History", options=[60, 180, 365, 730, 1825], value=180,
                            format_func=lambda d: f"{d} days")
    pid = by_label[choice]
    hist = prices[prices["product_id"] == pid]
    hist = hist[hist["date"] > hist["date"].max() - pd.Timedelta(days=days)]
    fc = pd.DataFrame(products[pid]["forecast"]).assign(date=lambda d: pd.to_datetime(d["date"]))
    band = alt.Chart(hist).mark_area(opacity=0.2).encode(
        x=alt.X("date:T", title=None), y=alt.Y("price_min:Q", title="Price (৳)"), y2="price_max:Q")
    line = alt.Chart(hist).mark_line().encode(x="date:T", y="price_mid:Q",
                                              tooltip=["date:T", "price_min", "price_max"])
    pred = alt.Chart(fc).mark_line(strokeDash=[4, 3], point=True, color="#d62728").encode(
        x="date:T", y="price:Q", tooltip=["date:T", "price", "change_pct"])
    st.altair_chart(band + line + pred, use_container_width=True)
    st.caption("Shaded band: TCB's lowest-highest price that day. Line: midpoint. Red dashes: forecast.")

with tab_health:
    if health and health.get("live_mape") is not None:
        h1, h2, h3 = st.columns(3)
        h1.metric("Live error, last 14 days (model)", f"{health['live_mape']:.2f}%")
        h2.metric("Live error, last 14 days (no-change baseline)", f"{health['live_naive_mape']:.2f}%")
        h3.metric("Backtest error promised", f"{health['backtest_mape']:.2f}%")
    else:
        st.write("Live accuracy appears once enough forecasts have been checked against real prices "
                 f"({(health or {}).get('live_rows', 0)} checked so far).")
    if not daily.empty:
        d = daily.melt(id_vars="target_date", value_vars=["mape_model", "mape_naive"],
                       var_name="series", value_name="MAPE %")
        st.altair_chart(alt.Chart(d).mark_line(point=True).encode(
            x=alt.X("target_date:T", title=None), y="MAPE %:Q", color="series:N"), use_container_width=True)
    if backtest:
        st.subheader("Backtest (26 weeks before launch)")
        st.dataframe(pd.DataFrame(backtest).T[["mape_model", "mape_naive", "mape_drift", "mape_ma7",
                                               "products_beating_naive", "products"]].round(2))
    if registry:
        st.subheader("Model decisions")
        st.dataframe(pd.DataFrame(registry["decisions"]).iloc[::-1], hide_index=True, width="stretch")
    if status:
        st.caption(f"Pipeline last updated {status['updated_at']} UTC · {status['price_rows']:,} price rows.")
