import pandas as pd
import streamlit as st

from src import data, indicators
from src.common import bootstrap

bootstrap("Screener", "📊")

st.title("📊 Stock Screener")
st.caption("Group and filter the full JSE universe by market-cap tier, GICS sector, and industry.")

universe = data.load_universe()

# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------
with st.container():
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.6, 1.6])
    with c1:
        tiers = st.multiselect(
            "Market-cap tier",
            options=["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"],
            default=[],
            placeholder="All tiers",
        )
    with c2:
        sectors = st.multiselect(
            "GICS sector",
            options=sorted(universe["gics_sector"].unique()),
            default=[],
            placeholder="All sectors",
        )
    with c3:
        available_industries = sorted(
            universe[universe["gics_sector"].isin(sectors)]["industry"].unique()
            if sectors
            else universe["industry"].unique()
        )
        industries = st.multiselect("Industry / Subsector", options=available_industries, default=[], placeholder="All industries")
    with c4:
        search = st.text_input("Search ticker or name", "")

filtered = universe.copy()
if tiers:
    filtered = filtered[filtered["market_cap_tier"].isin(tiers)]
if sectors:
    filtered = filtered[filtered["gics_sector"].isin(sectors)]
if industries:
    filtered = filtered[filtered["industry"].isin(industries)]
if search:
    s = search.strip().lower()
    filtered = filtered[
        filtered["symbol"].str.lower().str.contains(s) | filtered["name"].str.lower().str.contains(s)
    ]

st.caption(f"{len(filtered)} of {len(universe)} instruments match your filters.")

group_by = st.radio("Group by", ["None", "Market-cap tier", "GICS sector", "Industry"], horizontal=True)

# --------------------------------------------------------------------------
# Optional live price pull for the filtered set
# --------------------------------------------------------------------------
pull_live = st.checkbox(
    "Pull live price / % change / SMA signal for the filtered rows",
    value=len(filtered) <= 60,
    help="Fetches 1y of price history for every row shown. Uncheck for large lists to keep it fast.",
)

display_df = filtered[["symbol", "name", "market_cap_tier", "gics_sector", "industry", "market_cap_zar"]].rename(
    columns={
        "symbol": "Symbol",
        "name": "Name",
        "market_cap_tier": "Cap Tier",
        "gics_sector": "Sector",
        "industry": "Industry",
        "market_cap_zar": "Market Cap (ZAR)",
    }
)

if pull_live and len(filtered) > 0:
    progress = st.progress(0.0, text="Fetching price data...")

    def _cb(done, total):
        progress.progress(done / total, text=f"Fetching price data... chunk {done}/{total}")

    hist = data.get_history_bulk(filtered["yf_ticker"].tolist(), period="1y", interval="1d", progress_cb=_cb)
    progress.empty()

    last_prices, pct_changes, above200s = [], [], []
    for t in filtered["yf_ticker"]:
        df = hist.get(t)
        if df is None or df.empty:
            last_prices.append(None)
            pct_changes.append(None)
            above200s.append(None)
            continue
        last, pct = data.last_price_change(df)
        last_prices.append(last)
        pct_changes.append(pct)
        above200s.append(indicators.pct_above_sma(df, 200))

    display_df["Last Close"] = last_prices
    display_df["% Change"] = pct_changes
    display_df["Above 200-SMA"] = ["✅" if v else ("❌" if v is False else "—") for v in above200s]

if group_by == "None":
    st.dataframe(
        display_df.sort_values("Market Cap (ZAR)", ascending=False),
        hide_index=True,
        width="stretch",
        height=600,
    )
else:
    key = {"Market-cap tier": "Cap Tier", "GICS sector": "Sector", "Industry": "Industry"}[group_by]
    for group_name, group_df in display_df.groupby(key):
        with st.expander(f"{group_name}  ·  {len(group_df)} stocks", expanded=False):
            st.dataframe(
                group_df.sort_values("Market Cap (ZAR)", ascending=False),
                hide_index=True,
                width="stretch",
            )
