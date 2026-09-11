import pandas as pd
import plotly.express as px
import streamlit as st

from src import data, indicators
from src.common import bootstrap
from src.theme import DOWN, UP

bootstrap("Market Breadth", "🌡️")

st.title("🌡️ Market Breadth")
st.caption(
    "How many JSE-listed stocks are trading above their moving averages right now -- "
    "a classic gauge of whether a rally or selloff is broad-based or narrow."
)

universe = data.load_universe()

scope = st.radio(
    "Universe to scan",
    ["Mega + Large + Mid cap (fast)", "All JSE stocks (slower, ~1-2 min first run)"],
    horizontal=True,
)
if scope.startswith("Mega"):
    scan_universe = universe[universe["market_cap_tier"].isin(["Mega Cap", "Large Cap", "Mid Cap"])]
else:
    scan_universe = universe

sma_window = st.selectbox("SMA window", [20, 50, 100, 200], index=3)

run = st.button("Run breadth scan", type="primary")

if run:
    progress = st.progress(0.0, text="Fetching price data...")

    def _cb(done, total):
        progress.progress(done / total, text=f"Fetching price data... chunk {done}/{total}")

    hist = data.get_history_bulk(scan_universe["yf_ticker"].tolist(), period="18mo", interval="1d", progress_cb=_cb)
    progress.empty()

    rows = []
    for _, r in scan_universe.iterrows():
        df = hist.get(r["yf_ticker"])
        if df is None or df.empty or len(df) < sma_window:
            continue
        above = indicators.pct_above_sma(df, sma_window)
        if above is None:
            continue
        rows.append(
            {
                "Symbol": r["symbol"],
                "Sector": r["gics_sector"],
                "Industry": r["industry"],
                "Cap Tier": r["market_cap_tier"],
                f"Above {sma_window}-SMA": above,
            }
        )

    if not rows:
        st.error("No breadth data could be computed -- check your data connection (see scripts/test_data_connection.py).")
        st.stop()

    breadth_df = pd.DataFrame(rows)
    st.session_state["breadth_df"] = breadth_df
    st.session_state["breadth_sma"] = sma_window

if "breadth_df" not in st.session_state:
    st.info("Click **Run breadth scan** to compute breadth for the selected universe.")
    st.stop()

breadth_df = st.session_state["breadth_df"]
sma_window = st.session_state["breadth_sma"]
col_name = f"Above {sma_window}-SMA"

total = len(breadth_df)
above_count = int(breadth_df[col_name].sum())
pct = above_count / total * 100 if total else 0

st.divider()
m1, m2, m3 = st.columns(3)
m1.metric("Stocks scanned", total)
m2.metric(f"Above {sma_window}-day SMA", f"{above_count} ({pct:.1f}%)")
m3.metric(f"Below {sma_window}-day SMA", f"{total - above_count} ({100 - pct:.1f}%)")

fig = px.pie(
    values=[above_count, total - above_count],
    names=[f"Above {sma_window}-SMA", f"Below {sma_window}-SMA"],
    color_discrete_sequence=[UP, DOWN],
    hole=0.55,
)
fig.update_layout(height=320, margin=dict(t=10, b=10))
st.plotly_chart(fig, width="stretch")

st.subheader("Breadth by GICS sector")
sector_breadth = (
    breadth_df.groupby("Sector")[col_name]
    .agg(Above="sum", Total="count")
    .assign(Pct=lambda d: (d["Above"] / d["Total"] * 100).round(1))
    .sort_values("Pct", ascending=False)
    .reset_index()
)
fig2 = px.bar(
    sector_breadth,
    x="Pct",
    y="Sector",
    orientation="h",
    text=sector_breadth.apply(lambda r: f"{r['Above']}/{r['Total']} ({r['Pct']}%)", axis=1),
    color="Pct",
    color_continuous_scale=[DOWN, "#8B93A7", UP],
    range_color=[0, 100],
)
fig2.update_layout(height=420, coloraxis_showscale=False, xaxis_title=f"% above {sma_window}-SMA", yaxis_title="")
st.plotly_chart(fig2, width="stretch")

st.subheader("Breadth by industry / subsector")
sector_filter = st.multiselect("Filter to sector(s)", sorted(breadth_df["Sector"].unique()))
industry_scope = breadth_df[breadth_df["Sector"].isin(sector_filter)] if sector_filter else breadth_df
industry_breadth = (
    industry_scope.groupby("Industry")[col_name]
    .agg(Above="sum", Total="count")
    .assign(Pct=lambda d: (d["Above"] / d["Total"] * 100).round(1))
    .sort_values("Pct", ascending=False)
    .reset_index()
)
st.dataframe(industry_breadth, hide_index=True, width="stretch", height=420)

with st.expander("Show underlying stock-level data"):
    st.dataframe(breadth_df.sort_values(col_name, ascending=False), hide_index=True, width="stretch")
