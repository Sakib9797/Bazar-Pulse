"""Bazar Pulse dashboard (Streamlit Community Cloud entry point)."""

import html
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from hijridate import Hijri

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# Mid-tone colours that stay readable on both the light and the dark theme.
GREEN, RED, AMBER, INK = "#1E8A63", "#E5383B", "#E09F12", "#7D8F88"
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

T = {
    "tagline": (
        "Where Dhaka's essential-goods prices are likely to be in the next 4 weeks",
        "আগামী ৪ সপ্তাহে ঢাকার নিত্যপণ্যের দাম কোথায় থাকতে পারে",
    ),
    "tcb_data": ("TCB data", "টিসিবি তথ্য"),
    "products_n": ("{n} products", "{n}টি পণ্য"),
    "model": ("model", "মডেল"),
    "tab_outlook": ("🧭 Outlook", "🧭 পূর্বাভাস"),
    "tab_product": ("🔎 Product", "🔎 পণ্য"),
    "tab_basket": ("🧺 My basket", "🧺 আমার বাজার"),
    "tab_trends": ("📊 Trends", "📊 প্রবণতা"),
    "tab_health": ("🩺 Model health", "🩺 মডেলের অবস্থা"),
    "look_ahead": ("Look ahead", "কত সপ্তাহ পর"),
    "weeks": ("{n} week", "{n} সপ্তাহ"),
    "weeks_pl": ("{n} weeks", "{n} সপ্তাহ"),
    "category": ("Category", "ধরন"),
    "all": ("All", "সব"),
    "tracked": ("Products tracked", "মোট পণ্য"),
    "top_risk": ("Highest upside risk", "দাম বাড়ার সবচেয়ে বেশি ঝুঁকি"),
    "rise10": ("Could rise 10% or more", "১০% বা বেশি বাড়তে পারে"),
    "stable": ("Stable (within ±3%)", "স্থিতিশীল (±৩% এর মধ্যে)"),
    "updated": ("Data updated", "তথ্য হালনাগাদ"),
    "range_title": ("Where each price could be in {h}", "{h} পর কোন পণ্যের দাম কোথায় থাকতে পারে"),
    "range_help": (
        "Bar = 80% likely range, dot = most likely change vs today. Click a bar for details.",
        "দাগ = ৮০% সম্ভাব্য সীমা, বিন্দু = আজকের তুলনায় সবচেয়ে সম্ভাব্য পরিবর্তন। বিস্তারিত দেখতে দাগে ক্লিক করুন।",
    ),
    "show_all": ("Show all products", "সব পণ্য দেখান"),
    "change_axis": ("Change vs today (%)", "আজকের তুলনায় পরিবর্তন (%)"),
    "today": ("Today", "আজ"),
    "likely": ("Likely", "সম্ভাব্য"),
    "low": ("Low", "সর্বনিম্ন"),
    "high": ("High", "সর্বোচ্চ"),
    "range80": ("80% range", "৮০% সম্ভাব্য সীমা"),
    "in_h": ("In {h}", "{h} পর"),
    "reliable": (
        "Reliable: the range held the real price {p} of the time in testing",
        "নির্ভরযোগ্য: পরীক্ষায় {p} ক্ষেত্রে আসল দাম এই সীমার মধ্যে ছিল",
    ),
    "unreliable": (
        "Less reliable: the range held the real price only {p} of the time in testing",
        "কম নির্ভরযোগ্য: পরীক্ষায় মাত্র {p} ক্ষেত্রে আসল দাম এই সীমার মধ্যে ছিল",
    ),
    "spotlight": ("Selected product", "নির্বাচিত পণ্য"),
    "product": ("Product", "পণ্য"),
    "period": ("Period", "সময়কাল"),
    "last_year": ("Same time last year", "গত বছর এই সময়ে"),
    "chart_caption": (
        "Green band: TCB's lowest-highest price each day. Red: likely price and 80% range "
        "ahead. Dotted lines: Ramadan and Eid. Drag or scroll the chart to zoom.",
        "সবুজ অংশ: প্রতিদিন টিসিবির সর্বনিম্ন-সর্বোচ্চ দাম। লাল: সামনের সম্ভাব্য দাম ও ৮০% সীমা। "
        "ডটেড রেখা: রমজান ও ঈদ। জুম করতে চার্ট টানুন বা স্ক্রল করুন।",
    ),
    "basket_intro": (
        "Edit the list below (add or remove rows, change quantities) to see what your "
        "shopping could cost in {h}.",
        "নিচের তালিকা বদলান (সারি যোগ/বাদ দিন, পরিমাণ বদলান) এবং দেখুন {h} পর আপনার বাজার খরচ কত হতে পারে।",
    ),
    "item": ("Item", "পণ্য"),
    "qty": ("Quantity", "পরিমাণ"),
    "unit": ("Unit", "একক"),
    "cost_today": ("Cost today", "আজকের খরচ"),
    "cost_likely": ("Likely cost", "সম্ভাব্য খরচ"),
    "best_case": ("Best case", "সবচেয়ে ভালো হলে"),
    "worst_case": ("Worst case", "সবচেয়ে খারাপ হলে"),
    "basket_note": (
        "Best and worst case assume every item ends at the edge of its range at the same time, "
        "so the real total will usually be in between.",
        "সবচেয়ে ভালো ও খারাপ হিসাব ধরে নেয় সব পণ্যের দাম একসাথে সীমার প্রান্তে যাবে, তাই আসল খরচ সাধারণত এর মাঝামাঝি হবে।",
    ),
    "basket_empty": ("Add at least one item to the list.", "তালিকায় অন্তত একটি পণ্য যোগ করুন।"),
    "extra_cost": ("Extra cost in the worst case, by item (৳)", "সবচেয়ে খারাপ হলে কোন পণ্যে কত বাড়তি খরচ (৳)"),
    "compare": ("Compare products", "পণ্য তুলনা করুন"),
    "as_index": ("Show as index (start = 100)", "সূচক হিসেবে দেখান (শুরু = ১০০)"),
    "price_axis": ("Price (৳)", "দাম (৳)"),
    "index_axis": ("Index (start = 100)", "সূচক (শুরু = ১০০)"),
    "trend_caption": (
        "Gaps are periods missing from TCB's own archive (mostly 2022).",
        "ফাঁকা অংশগুলো টিসিবির আর্কাইভেই নেই (বেশিরভাগ ২০২২ সালের)।",
    ),
    "cat_change": (
        "Typical price change by group over this period",
        "এই সময়ে প্রতিটি ধরনের দামের সাধারণ পরিবর্তন",
    ),
    "live_cov": ("Live range coverage", "বাস্তবে সীমার মধ্যে দাম"),
    "target": ("target {p}", "লক্ষ্য {p}"),
    "skill": ("Better than baseline (backtest)", "বেসলাইনের চেয়ে ভালো (পরীক্ষায়)"),
    "checks": ("Forecasts checked so far", "এ পর্যন্ত যাচাই করা পূর্বাভাস"),
    "champion": ("Champion model", "বর্তমান মডেল"),
    "warming": (
        "Live accuracy appears once enough forecasts reach their dates (the first ones mature after a week).",
        "যথেষ্ট পূর্বাভাসের তারিখ এলে বাস্তব নির্ভুলতা দেখা যাবে (প্রথমগুলো এক সপ্তাহ পর)।",
    ),
    "cov_chart": ("Share of real prices inside the forecast range", "পূর্বাভাসের সীমার মধ্যে থাকা আসল দামের হার"),
    "backtest": ("Backtest before launch (26 weeks)", "চালুর আগে পরীক্ষা (২৬ সপ্তাহ)"),
    "decisions": ("Model decisions", "মডেল সংক্রান্ত সিদ্ধান্ত"),
    "how_title": ("How does this work?", "এটি কীভাবে কাজ করে?"),
    "how_body": (
        "Every day the system downloads the Trading Corporation of Bangladesh's price sheet, checks it, and "
        "compares earlier forecasts with the real prices. A machine-learning model then predicts a **low**, "
        "**likely** and **high** price for each product 1-4 weeks ahead, tuned so the real price lands "
        "inside that range about 80% of the time. Exact prices are rarely predictable (most prices stay "
        "flat for weeks), so the useful part is the range: how far a price could move. Every week new "
        "models compete, and one only replaces the current model if it is measurably better.",
        "প্রতিদিন সিস্টেমটি ট্রেডিং কর্পোরেশন অব বাংলাদেশের দামের তালিকা নামায়, যাচাই করে, আর আগের পূর্বাভাস আসল "
        "দামের সাথে মেলায়। এরপর একটি মেশিন-লার্নিং মডেল প্রতিটি পণ্যের ১-৪ সপ্তাহ পরের **সর্বনিম্ন**, "
        "**সম্ভাব্য** ও **সর্বোচ্চ** দাম অনুমান করে, যাতে প্রায় ৮০% ক্ষেত্রে আসল দাম সেই সীমার মধ্যে থাকে। হুবহু "
        "দাম আগে থেকে বলা কঠিন (বেশিরভাগ দাম সপ্তাহের পর সপ্তাহ একই থাকে), তাই আসল কাজের তথ্য হলো সীমা: দাম "
        "কতটা ওঠানামা করতে পারে। প্রতি সপ্তাহে নতুন মডেল প্রতিযোগিতা করে, আর স্পষ্টভাবে ভালো হলেই কেবল "
        "বর্তমান মডেলকে বদলায়।",
    ),
    "disclaimer": (
        "Source: Trading Corporation of Bangladesh (TCB) daily retail prices, Dhaka. Forecasts are "
        "estimates for information only, not official prices.",
        "উৎস: ট্রেডিং কর্পোরেশন অব বাংলাদেশ (টিসিবি)-এর ঢাকার দৈনিক খুচরা বাজারদর। পূর্বাভাস শুধু তথ্যের জন্য, সরকারি দাম নয়।",
    ),
    "no_data": ("No forecast has been produced yet.", "এখনো কোনো পূর্বাভাস তৈরি হয়নি।"),
    "theme_help": (
        "**Light or dark?** The dashboard follows your phone or computer setting. To switch by hand, open "
        "the **⋮** menu (top right) → **Settings** → **Theme** and choose Light, Dark or System.",
        "**লাইট না ডার্ক?** ড্যাশবোর্ডটি আপনার ফোন বা কম্পিউটারের সেটিং অনুযায়ী চলে। নিজে বদলাতে উপরে ডানে "
        "**⋮** মেনু → **Settings** → **Theme** থেকে Light, Dark বা System বেছে নিন।",
    ),
    "theme_hint": ("🌙 Dark mode: ⋮ → Settings → Theme", "🌙 ডার্ক মোড: ⋮ → Settings → Theme"),
}
CATEGORY = {
    "rice": ("Rice", "চাল"),
    "flour": ("Flour", "আটা-ময়দা"),
    "edible_oil": ("Edible oil", "ভোজ্য তেল"),
    "pulses": ("Pulses", "ডাল"),
    "vegetables": ("Vegetables", "সবজি"),
    "spices": ("Spices", "মসলা"),
    "fish_meat": ("Fish & meat", "মাছ-মাংস"),
    "milk_powder": ("Milk powder", "গুঁড়া দুধ"),
    "groceries": ("Groceries", "মুদি"),
    "stationery": ("Stationery", "কাগজ"),
    "construction": ("Construction", "নির্মাণ"),
}
UNIT_BN = {
    "kg": "কেজি",
    "kg packet": "কেজি (প্যাকেট)",
    "litre": "লিটার",
    "5 L bottle": "৫ লিটার বোতল",
    "2 L bottle": "২ লিটার বোতল",
    "1 L bottle": "১ লিটার বোতল",
    "1 kg packet": "১ কেজি প্যাকেট",
    "hali (4 eggs)": "হালি (৪টি)",
    "hali (4 pcs)": "হালি (৪টি)",
    "dista (24 sheets)": "দিস্তা",
    "metric ton": "মেট্রিক টন",
}
EVENTS = {
    "ramadan": ("Ramadan", "রমজান"),
    "fitr": ("Eid al-Fitr", "ঈদুল ফিতর"),
    "adha": ("Eid al-Adha", "ঈদুল আজহা"),
}
BASKET = [
    ("rice_coarse", 25),
    ("atta_loose", 5),
    ("soybean_oil_5l", 1),
    ("lentil_masur_large", 3),
    ("potato", 10),
    ("onion_local", 5),
    ("egg_farm", 8),
    ("sugar", 2),
    ("salt_iodized", 1),
    ("chicken_broiler", 3),
]
CSS = """
<style>
.block-container {padding-top: 2.6rem; max-width: 1250px;}
.bp-hero {background: linear-gradient(120deg, #00563F 0%, #006A4E 45%, #12946B 100%); color: #fff;
  border-radius: 20px; padding: 22px 28px 18px; margin-bottom: 6px; box-shadow: 0 8px 24px rgba(0,80,58,.18);}
.bp-hero h1 {color: #fff; margin: 0; font-size: 2.2rem; line-height: 1.2; padding: 0;}
.bp-hero .sub {opacity: .93; margin-top: 4px; font-size: 1.02rem;}
.bp-chip {display: inline-block; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25);
  padding: 3px 12px; border-radius: 999px; margin: 12px 8px 0 0; font-size: .86rem;}
.bp-dot {display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #7CF5B5;
  margin-right: 6px; box-shadow: 0 0 0 3px rgba(124,245,181,.25);}
.bp-card {border: 1px solid rgba(0,106,78,.18); background: rgba(0,106,78,.05); border-radius: 16px;
  padding: 16px 18px;}
.bp-card h3 {margin: 0 0 2px 0; font-size: 1.25rem;}
.bp-card .muted {opacity: .7; font-size: .9rem;}
.bp-range {position: relative; height: 12px; border-radius: 999px; margin: 14px 0 6px;
  background: linear-gradient(90deg, #2E9E6B, #F5B700 60%, #E5383B);}
.bp-range .mark {position: absolute; top: -5px; width: 4px; height: 22px; border-radius: 2px;
  background: #18302A; box-shadow: 0 0 0 2px rgba(255,255,255,.85);}
.bp-scale {display: flex; justify-content: space-between; font-size: .85rem; opacity: .85;}
div[data-testid="stMetric"] {background: rgba(30,138,99,.07); border-radius: 14px;}
.bp-card {background: rgba(30,138,99,.07); border-color: rgba(30,138,99,.28);}
.stTabs [data-baseweb="tab-list"] {gap: 6px;}
.stTabs [data-baseweb="tab"] {padding: 8px 14px; border-radius: 10px 10px 0 0;}
</style>
"""

st.set_page_config(page_title="Bazar Pulse | বাজার পালস", page_icon="🛒", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@st.cache_data(ttl=600)
def load():
    latest = read_json(DATA / "forecasts" / "latest.json")
    prices = pd.read_parquet(
        DATA / "clean" / "prices.parquet",
        columns=["date", "product_id", "price_min", "price_max", "price_mid"],
    )
    daily_path = DATA / "monitoring" / "daily_metrics.parquet"
    daily = pd.read_parquet(daily_path) if daily_path.exists() else pd.DataFrame()
    return {
        "latest": latest,
        "prices": prices,
        "daily": daily,
        "status": read_json(DATA / "status.json"),
        "health": read_json(DATA / "monitoring" / "health.json"),
        "registry": read_json(ROOT / "models" / "registry.json"),
        "backtest": read_json(ROOT / "reports" / "backtest.json"),
        "product_bt": read_json(ROOT / "reports" / "backtest_products.json") or {},
    }


@st.cache_data
def islamic_events(first_year=1442, last_year=1450):
    rows = []
    for y in range(first_year, last_year + 1):
        for key, (m, d) in {"ramadan": (9, 1), "fitr": (10, 1), "adha": (12, 10)}.items():
            rows.append({"date": pd.Timestamp(Hijri(y, m, d).to_gregorian()), "event": key})
    return pd.DataFrame(rows)


d = load()
latest = d["latest"]
_, theme_col, lang_col = st.columns([4.6, 0.5, 1.2], vertical_alignment="center")
lang_choice = lang_col.segmented_control(
    "Language", ["English", "বাংলা"], default="English", key="lang", label_visibility="collapsed"
)
BN = lang_choice == "বাংলা"


def t(key, **kw):
    s = T[key][1 if BN else 0]
    return s.format(**kw) if kw else s


def num(x, digits=0):
    s = f"{x:,.{digits}f}"
    return s.translate(BN_DIGITS) if BN else s


def pct(x, digits=1, sign=True):
    s = f"{x:+.{digits}f}%" if sign else f"{x:.{digits}f}%"
    return s.translate(BN_DIGITS) if BN else s


def weeks_label(n):
    return t("weeks" if n == 1 else "weeks_pl", n=num(n))


def name(p):
    return p["name_bn"] if BN else p["name_en"]


def unit(p):
    return UNIT_BN.get(p["unit"], p["unit"]) if BN else p["unit"]


def cat_label(c):
    return CATEGORY.get(c, (c, c))[1 if BN else 0]


with theme_col.popover("🌙", help="Light / dark theme"):
    st.markdown(t("theme_help"))

if not latest:
    st.error(t("no_data"))
    st.stop()

meta = {p["product_id"]: p for p in latest["products"]}
fc = pd.DataFrame(
    [
        {"product_id": p["product_id"], "last": p["last_price"], **f}
        for p in latest["products"]
        for f in p["forecast"]
    ]
)
fc["date"] = pd.to_datetime(fc["date"])
fc["low_pct"] = (fc["low"] / fc["last"] - 1) * 100
fc["mid_pct"] = (fc["mid"] / fc["last"] - 1) * 100
fc["high_pct"] = (fc["high"] / fc["last"] - 1) * 100
fc["name"] = fc["product_id"].map(lambda p: name(meta[p]))
fc["category"] = fc["product_id"].map(lambda p: meta[p]["category"])
coverage_target = latest.get("coverage_target", 0.8)
champ = (d["registry"] or {}).get("champion") or {}

origin = pd.Timestamp(latest["origin_date"])
status_line = (
    f"{t('tcb_data')}: {origin:%d %b %Y}"
    if not BN
    else f"{t('tcb_data')}: {num(origin.day)}/{num(origin.month)}/{num(origin.year).replace(',', '')}"
)
st.markdown(
    f"""
<div class="bp-hero">
  <h1>🛒 Bazar Pulse <span style="font-weight:400; opacity:.85">· বাজার পালস</span></h1>
  <div class="sub">{html.escape(t("tagline"))}</div>
  <span class="bp-chip"><span class="bp-dot"></span>{html.escape(status_line)}</span>
  <span class="bp-chip">{html.escape(t("products_n", n=num(len(meta))))}</span>
  <span class="bp-chip">{html.escape(t("model"))}: v{champ.get("version", "?")} ·
    {html.escape(champ.get("config", {}).get("name", "-"))}</span>
</div>""",
    unsafe_allow_html=True,
)


def reliability(pid):
    bt = d["product_bt"].get(pid)
    if not bt:
        return
    p = pct(bt["coverage"] * 100, 0, sign=False)
    if bt["coverage"] < 0.65:
        st.badge(t("unreliable", p=p), icon=":material/warning:", color="orange")
    else:
        st.badge(t("reliable", p=p), icon=":material/verified:", color="green")


def range_card(pid, weeks):
    p, f = meta[pid], fc[(fc["product_id"] == pid) & (fc["weeks"] == weeks)].iloc[0]
    lo, hi = min(f["low_pct"], -1), max(f["high_pct"], 1)
    pos = (0 - lo) / (hi - lo) * 100
    mid_pos = (f["mid_pct"] - lo) / (hi - lo) * 100
    st.markdown(
        f"""
<div class="bp-card">
  <div class="muted">{html.escape(cat_label(p["category"]))} · {html.escape(unit(p))}</div>
  <h3>{html.escape(name(p))}</h3>
  <div class="bp-range"><div class="mark" style="left:{pos:.1f}%; opacity:.45"></div>
    <div class="mark" style="left:{mid_pos:.1f}%"></div></div>
  <div class="bp-scale"><span>{t("low")} ৳{num(f["low"], 1)}</span>
    <span>{t("likely")} ৳{num(f["mid"], 1)}</span>
    <span>{t("high")} ৳{num(f["high"], 1)}</span></div>
</div>""",
        unsafe_allow_html=True,
    )


tabs = st.tabs([t("tab_outlook"), t("tab_product"), t("tab_basket"), t("tab_trends"), t("tab_health")])

# ---------------------------------------------------------------- Outlook
with tabs[0]:
    c1, c2 = st.columns([1.5, 3])
    weeks = (
        c1.segmented_control(
            t("look_ahead"), [1, 2, 3, 4], default=4, key="outlook_weeks", format_func=weeks_label
        )
        or 4
    )
    cats = sorted(fc["category"].unique(), key=cat_label)
    picked = c2.pills(t("category"), cats, selection_mode="multi", key="outlook_cats", format_func=cat_label)
    now = fc[fc["weeks"] == weeks]
    if picked:
        now = now[now["category"].isin(picked)]

    k1, k2, k3, k4 = st.columns(4)
    top = now.sort_values("high_pct", ascending=False).iloc[0]
    k1.metric(t("tracked"), num(now["product_id"].nunique()), border=True)
    k2.metric(t("top_risk"), top["name"], pct(top["high_pct"], 0), delta_color="inverse", border=True)
    k3.metric(t("rise10"), num(int((now["high_pct"] >= 10).sum())), border=True)
    k4.metric(t("stable"), num(int(((now["high_pct"] <= 3) & (now["low_pct"] >= -3)).sum())), border=True)

    h = weeks_label(weeks)
    st.subheader(t("range_title", h=h))
    st.caption(t("range_help"))
    show_all = st.toggle(t("show_all"), value=False, key="outlook_all")
    view = now.sort_values("high_pct", ascending=False)
    if not show_all:
        view = view.head(15)
    pick = alt.selection_point(name="pick", fields=["product_id"], on="click")
    tooltip = [
        alt.Tooltip("name:N", title=t("product")),
        alt.Tooltip("last:Q", title=f"{t('today')} ৳"),
        alt.Tooltip("low:Q", title=f"{t('low')} ৳", format=",.1f"),
        alt.Tooltip("mid:Q", title=f"{t('likely')} ৳", format=",.1f"),
        alt.Tooltip("high:Q", title=f"{t('high')} ৳", format=",.1f"),
        alt.Tooltip("high_pct:Q", title="↑ %", format="+.1f"),
    ]
    y = alt.Y("name:N", sort=list(view["name"]), title=None, axis=alt.Axis(labelLimit=260, labelFontSize=12))
    bars = (
        alt.Chart(view)
        .mark_rule(strokeWidth=11, strokeCap="round")
        .encode(
            y=y,
            x=alt.X("low_pct:Q", title=t("change_axis")),
            x2="high_pct:Q",
            color=alt.Color(
                "high_pct:Q",
                legend=None,
                scale=alt.Scale(domain=[0, 10, 30], range=["#2E9E6B", "#F5B700", RED], clamp=True),
            ),
            opacity=alt.condition(pick, alt.value(0.95), alt.value(0.3)),
            tooltip=tooltip,
        )
        .add_params(pick)
    )
    dots = alt.Chart(view).mark_circle(size=70, color=INK).encode(y=y, x="mid_pct:Q", tooltip=tooltip)
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(strokeDash=[4, 4], color="#7a8a85").encode(x="x:Q")
    event = st.altair_chart(
        (bars + dots + zero).properties(height=max(240, 27 * len(view))),
        on_select="rerun",
        key="outlook_chart",
        use_container_width=True,
    )
    chosen = (event.selection.get("pick") or [{}])[0].get("product_id") if event else None
    spot = chosen or view.iloc[0]["product_id"]

    st.markdown(f"#### {t('spotlight')}")
    left, right = st.columns([1, 1.3])
    with left:
        range_card(spot, weeks)
        reliability(spot)
    with right:
        sp = fc[fc["product_id"] == spot]
        start = pd.DataFrame(
            {
                "date": [origin],
                "low": [meta[spot]["last_price"]],
                "mid": [meta[spot]["last_price"]],
                "high": [meta[spot]["last_price"]],
            }
        )
        sp = pd.concat([start, sp[["date", "low", "mid", "high"]]], ignore_index=True)
        mini = alt.Chart(sp).mark_area(opacity=0.22, color=RED).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("low:Q", title="৳", scale=alt.Scale(zero=False)),
            y2="high:Q",
        ) + alt.Chart(sp).mark_line(
            point=alt.OverlayMarkDef(color=RED, filled=True), color=RED, strokeDash=[5, 4]
        ).encode(
            x="date:T",
            y="mid:Q",
            tooltip=[
                alt.Tooltip("date:T"),
                alt.Tooltip("low:Q", format=",.1f"),
                alt.Tooltip("mid:Q", format=",.1f"),
                alt.Tooltip("high:Q", format=",.1f"),
            ],
        )
        st.altair_chart(mini.properties(height=210), use_container_width=True)

# ---------------------------------------------------------------- Product
with tabs[1]:
    labels = {pid: f"{name(p)} ({unit(p)})" for pid, p in sorted(meta.items(), key=lambda kv: name(kv[1]))}
    ids = list(labels)
    default = ids.index(spot) if spot in ids else 0
    c1, c2 = st.columns([2, 1.4])
    pid = c1.selectbox(t("product"), ids, index=default, format_func=labels.get, key=f"product_pick_{BN}")
    span = (
        c2.segmented_control(t("period"), ["3M", "6M", "1Y", "2Y", "5Y"], default="1Y", key="product_span")
        or "1Y"
    )
    days = {"3M": 92, "6M": 183, "1Y": 365, "2Y": 730, "5Y": 1900}[span]
    p = meta[pid]
    all_hist = d["prices"][d["prices"]["product_id"] == pid].sort_values("date")
    hist = all_hist[all_hist["date"] > origin - pd.Timedelta(days=days)]
    f4 = fc[(fc["product_id"] == pid) & (fc["weeks"] == 4)].iloc[0]
    ago = all_hist[(all_hist["date"] - (origin - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=7)]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("today"), f"৳{num(p['last_price'], 1)}", border=True)
    m2.metric(
        t("in_h", h=weeks_label(4)),
        f"৳{num(f4['mid'], 1)}",
        pct(f4["mid_pct"]),
        delta_color="inverse",
        border=True,
    )
    m3.metric(t("range80"), f"৳{num(f4['low'], 0)}–{num(f4['high'], 0)}", border=True)
    if len(ago):
        then = ago.iloc[(ago["date"] - (origin - pd.Timedelta(days=365))).abs().argmin()]["price_mid"]
        m4.metric(
            t("last_year"),
            f"৳{num(then, 1)}",
            pct((p["last_price"] / then - 1) * 100),
            delta_color="inverse",
            border=True,
            help="Change from then to today" if not BN else "তখন থেকে আজ পর্যন্ত পরিবর্তন",
        )
    else:
        m4.metric(
            t("last_year"),
            "–",
            border=True,
            help="TCB had no price for this item a year ago"
            if not BN
            else "এক বছর আগে টিসিবির তালিকায় এই পণ্যের দাম ছিল না",
        )
    reliability(pid)

    fpts = pd.concat(
        [
            pd.DataFrame(
                {
                    "date": [origin],
                    "low": [p["last_price"]],
                    "mid": [p["last_price"]],
                    "high": [p["last_price"]],
                }
            ),
            fc[fc["product_id"] == pid][["date", "low", "mid", "high"]],
        ],
        ignore_index=True,
    )
    ev = islamic_events()
    ev = ev[(ev["date"] >= hist["date"].min()) & (ev["date"] <= fpts["date"].max())].copy()
    ev["label"] = ev["event"].map(lambda e: EVENTS[e][1 if BN else 0])
    zoom = alt.selection_interval(bind="scales", encodings=["x"])
    hover = alt.selection_point(
        fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout"
    )
    x = alt.X("date:T", title=None)
    band = (
        alt.Chart(hist)
        .mark_area(opacity=0.22, color=GREEN)
        .encode(
            x=x, y=alt.Y("price_min:Q", title=t("price_axis"), scale=alt.Scale(zero=False)), y2="price_max:Q"
        )
        .add_params(zoom)
    )
    line = alt.Chart(hist).mark_line(color=GREEN, strokeWidth=2).encode(x=x, y="price_mid:Q")
    hover_pts = (
        alt.Chart(hist)
        .mark_circle(size=70, color=GREEN)
        .encode(
            x=x,
            y="price_mid:Q",
            opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=[
                alt.Tooltip("date:T"),
                alt.Tooltip("price_min:Q", title=t("low")),
                alt.Tooltip("price_max:Q", title=t("high")),
            ],
        )
        .add_params(hover)
    )
    fband = alt.Chart(fpts).mark_area(opacity=0.25, color=RED).encode(x=x, y="low:Q", y2="high:Q")
    fline = (
        alt.Chart(fpts)
        .mark_line(color=RED, strokeDash=[5, 4], point=alt.OverlayMarkDef(color=RED, filled=True))
        .encode(
            x=x,
            y="mid:Q",
            tooltip=[
                alt.Tooltip("date:T"),
                alt.Tooltip("low:Q", title=t("low"), format=",.1f"),
                alt.Tooltip("mid:Q", title=t("likely"), format=",.1f"),
                alt.Tooltip("high:Q", title=t("high"), format=",.1f"),
            ],
        )
    )
    layers = [band, line, hover_pts, fband, fline]
    if len(ev):
        layers += [
            alt.Chart(ev)
            .mark_rule(strokeDash=[2, 3], color=AMBER, strokeWidth=1.5)
            .encode(x=x, tooltip=[alt.Tooltip("label:N", title=""), alt.Tooltip("date:T")]),
            alt.Chart(ev)
            .mark_text(angle=270, align="right", dx=-6, dy=-5, color=AMBER, fontSize=11, fontWeight="bold")
            .encode(x=x, y=alt.value(4), text="label:N"),
        ]
    st.altair_chart(alt.layer(*layers).properties(height=420), use_container_width=True)
    st.caption(t("chart_caption"))
    table = fc[fc["product_id"] == pid][["date", "weeks", "low", "mid", "high", "mid_pct", "high_pct"]]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "date": st.column_config.DateColumn(t("period"), format="D MMM YYYY"),
            "weeks": st.column_config.NumberColumn("⏱", format="%d"),
            "low": st.column_config.NumberColumn(f"{t('low')} ৳", format="%.1f"),
            "mid": st.column_config.NumberColumn(f"{t('likely')} ৳", format="%.1f"),
            "high": st.column_config.NumberColumn(f"{t('high')} ৳", format="%.1f"),
            "mid_pct": st.column_config.NumberColumn(f"{t('likely')} %", format="%+.1f%%"),
            "high_pct": st.column_config.NumberColumn(f"{t('high')} %", format="%+.1f%%"),
        },
    )

# ---------------------------------------------------------------- Basket
with tabs[2]:
    bweeks = (
        st.segmented_control(
            t("look_ahead"), [1, 2, 3, 4], default=4, key="basket_weeks", format_func=weeks_label
        )
        or 4
    )
    st.write(t("basket_intro", h=weeks_label(bweeks)))
    label_of = {pid: f"{name(p)} · {unit(p)}" for pid, p in meta.items()}
    pid_of = {v: k for k, v in label_of.items()}
    start_rows = pd.DataFrame([{"item": label_of[pid], "qty": q} for pid, q in BASKET if pid in meta])
    edited = st.data_editor(
        start_rows,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key=f"basket_{BN}",
        column_config={
            "item": st.column_config.SelectboxColumn(
                t("item"), options=sorted(label_of.values()), required=True, width="large"
            ),
            "qty": st.column_config.NumberColumn(
                t("qty"), min_value=0.0, step=0.5, format="%.1f", required=True
            ),
        },
    )
    rows = edited.dropna().assign(product_id=lambda df: df["item"].map(pid_of)).dropna(subset=["product_id"])
    rows = rows.merge(
        fc[fc["weeks"] == bweeks][["product_id", "last", "low", "mid", "high"]], on="product_id"
    )
    if rows.empty:
        st.info(t("basket_empty"))
    else:
        for col in ("last", "low", "mid", "high"):
            rows[f"cost_{col}"] = rows[col] * rows["qty"]
        today_total = rows["cost_last"].sum()
        b1, b2, b3, b4 = st.columns(4)
        b1.metric(t("cost_today"), f"৳{num(today_total)}", border=True)
        for col, key, box in (
            ("mid", "cost_likely", b2),
            ("low", "best_case", b3),
            ("high", "worst_case", b4),
        ):
            total = rows[f"cost_{col}"].sum()
            diff = total - today_total
            box.metric(
                t(key),
                f"৳{num(total)}",
                f"{'-' if diff < 0 else '+'}৳{num(abs(diff))}",
                delta_color="inverse",
                border=True,
            )
        st.caption(t("basket_note"))
        rows["extra"] = rows["cost_high"] - rows["cost_last"]
        rows["label"] = rows["product_id"].map(lambda p: name(meta[p]))
        extra = rows[rows["extra"] > 0.5].sort_values("extra", ascending=False)
        if len(extra):
            st.markdown(f"#### {t('extra_cost')}")
            st.altair_chart(
                alt.Chart(extra)
                .mark_bar(cornerRadiusEnd=6, color=RED, opacity=0.85)
                .encode(
                    x=alt.X("extra:Q", title="৳"),
                    y=alt.Y("label:N", sort="-x", title=None),
                    tooltip=[
                        alt.Tooltip("label:N", title=t("item")),
                        alt.Tooltip("extra:Q", title="৳", format=",.0f"),
                    ],
                )
                .properties(height=max(160, 30 * len(extra))),
                use_container_width=True,
            )

# ---------------------------------------------------------------- Trends
with tabs[3]:
    defaults = [
        x for x in ("onion_local", "rice_coarse", "soybean_oil_loose", "egg_farm", "potato") if x in meta
    ]
    c1, c2 = st.columns([3, 1.4])
    chosen_ids = c1.multiselect(
        t("compare"), ids, default=defaults, format_func=labels.get, max_selections=8, key=f"trend_pick_{BN}"
    )
    tspan = c2.segmented_control(t("period"), ["1Y", "2Y", "5Y"], default="2Y", key="trend_span") or "2Y"
    as_index = st.toggle(t("as_index"), value=True, key="trend_index")
    since = origin - pd.Timedelta(days={"1Y": 365, "2Y": 730, "5Y": 1900}[tspan])
    tp = d["prices"][(d["prices"]["date"] > since)]
    if chosen_ids:
        series = tp[tp["product_id"].isin(chosen_ids)].copy()
        series["name"] = series["product_id"].map(lambda q: name(meta[q]))
        # Weekly means: smoother lines, and gaps in TCB's archive stay visible as breaks.
        series = series.set_index("date").groupby("name")["price_mid"].resample("W").mean().reset_index()
        if as_index:
            start_price = series.dropna().groupby("name")["price_mid"].first()
            series["value"] = series["price_mid"] / series["name"].map(start_price) * 100
        else:
            series["value"] = series["price_mid"]
        nearest = alt.selection_point(
            fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout"
        )
        base = alt.Chart(series).encode(x=alt.X("date:T", title=None))
        lines = base.mark_line(strokeWidth=2.2, interpolate="monotone").encode(
            y=alt.Y(
                "value:Q", title=t("index_axis") if as_index else t("price_axis"), scale=alt.Scale(zero=False)
            ),
            color=alt.Color("name:N", legend=alt.Legend(orient="top", title=None, labelLimit=240)),
        )
        rule = (
            base.mark_rule(color="#7a8a85")
            .encode(
                opacity=alt.condition(nearest, alt.value(0.6), alt.value(0)), tooltip=[alt.Tooltip("date:T")]
            )
            .add_params(nearest)
        )
        pts = lines.mark_circle(size=55).encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
            tooltip=[
                alt.Tooltip("name:N", title=""),
                alt.Tooltip("date:T"),
                alt.Tooltip("value:Q", format=",.1f", title=""),
            ],
        )
        zoom = alt.selection_interval(bind="scales", encodings=["x"])
        st.altair_chart(
            alt.layer(lines.add_params(zoom), rule, pts).properties(height=380), use_container_width=True
        )
        st.caption(t("trend_caption"))

    st.markdown(f"#### {t('cat_change')}")
    first_month = (
        tp[tp["date"] <= tp["date"].min() + pd.Timedelta(days=30)].groupby("product_id")["price_mid"].mean()
    )
    last_month = tp[tp["date"] > origin - pd.Timedelta(days=30)].groupby("product_id")["price_mid"].mean()
    change = ((last_month / first_month - 1) * 100).dropna().rename("change").reset_index()
    change = change[change["product_id"].isin(meta)]
    change["category"] = change["product_id"].map(lambda q: meta[q]["category"])
    by_cat = change.groupby("category")["change"].median().reset_index()
    by_cat["label"] = by_cat["category"].map(cat_label)
    st.altair_chart(
        alt.Chart(by_cat)
        .mark_bar(cornerRadiusEnd=6)
        .encode(
            x=alt.X("change:Q", title="%"),
            y=alt.Y("label:N", sort="-x", title=None),
            color=alt.condition("datum.change > 0", alt.value(RED), alt.value("#2E9E6B")),
            tooltip=[
                alt.Tooltip("label:N", title=t("category")),
                alt.Tooltip("change:Q", format="+.1f", title="%"),
            ],
        )
        .properties(height=34 * len(by_cat)),
        use_container_width=True,
    )

# ---------------------------------------------------------------- Model health
with tabs[4]:
    health = d["health"] or {}
    bt = (d["backtest"] or {}).get(champ.get("config", {}).get("name"), {})
    h1, h2, h3, h4 = st.columns(4)
    h1.metric(
        f"{t('champion')} · {champ.get('config', {}).get('name', '-')}",
        f"v{champ.get('version', '?')}",
        border=True,
    )
    if bt:
        h2.metric(t("skill"), pct(bt["skill"] * 100), border=True)
    live_cov = health.get("live_coverage")
    h3.metric(
        f"{t('live_cov')} ({t('target', p=pct(coverage_target * 100, 0, sign=False))})",
        pct(live_cov * 100, 0, sign=False) if live_cov is not None else "–",
        border=True,
    )
    h4.metric(t("checks"), num(health.get("live_rows", 0)), border=True)
    if health.get("live_coverage") is None:
        st.info(t("warming"))
    daily = d["daily"]
    if not daily.empty:
        st.markdown(f"#### {t('cov_chart')}")
        cov = daily.melt(
            id_vars="target_date",
            value_vars=["coverage", "coverage_climatology"],
            var_name="series",
            value_name="share",
        )
        cov["series"] = cov["series"].map(
            {"coverage": t("model").capitalize(), "coverage_climatology": "baseline" if not BN else "বেসলাইন"}
        )
        target_rule = (
            alt.Chart(pd.DataFrame({"y": [coverage_target]}))
            .mark_rule(strokeDash=[6, 4], color=GREEN)
            .encode(y="y:Q")
        )
        st.altair_chart(
            (
                alt.Chart(cov)
                .mark_line(point=True)
                .encode(
                    x=alt.X("target_date:T", title=None),
                    y=alt.Y("share:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1]), title=None),
                    color=alt.Color("series:N", legend=alt.Legend(orient="top", title=None)),
                    tooltip=[alt.Tooltip("target_date:T"), alt.Tooltip("share:Q", format=".0%"), "n:Q"],
                )
                + target_rule
            ).properties(height=280),
            use_container_width=True,
        )
    with st.expander(t("how_title"), expanded=False, icon=":material/help:"):
        st.markdown(t("how_body"))
    if d["backtest"]:
        st.markdown(f"#### {t('backtest')}")
        frame = (
            pd.DataFrame(d["backtest"])
            .T[
                [
                    "pinball_model",
                    "pinball_climatology",
                    "skill",
                    "coverage_model",
                    "width_model",
                    "products_beating_climatology",
                    "products",
                ]
            ]
            .astype(float)
        )
        st.dataframe(
            frame,
            width="stretch",
            column_config={
                "pinball_model": st.column_config.NumberColumn("pinball", format="%.4f"),
                "pinball_climatology": st.column_config.NumberColumn("baseline", format="%.4f"),
                "skill": st.column_config.ProgressColumn(
                    "skill", format="percent", min_value=0, max_value=0.1
                ),
                "coverage_model": st.column_config.ProgressColumn(
                    "coverage", format="percent", min_value=0, max_value=1
                ),
                "width_model": st.column_config.NumberColumn("width %", format="%.2f"),
                "products_beating_climatology": st.column_config.NumberColumn("products better"),
                "products": st.column_config.NumberColumn("of"),
            },
        )
    if d["registry"]:
        st.markdown(f"#### {t('decisions')}")
        dec = pd.DataFrame(d["registry"]["decisions"]).iloc[::-1]
        cols = [c for c in ("at", "kind", "version", "promoted", "reason") if c in dec]
        st.dataframe(dec[cols], hide_index=True, width="stretch")

st.divider()
st.caption(f"{t('disclaimer')} · {t('theme_hint')} · [GitHub](https://github.com/Sakib9797/Bazar-Pulse)")
