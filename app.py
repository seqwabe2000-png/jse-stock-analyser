"""
JSE Stock Analyser -- entry point.

Run with:  streamlit run app.py
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from src import data, indicators
from src.common import bootstrap

bootstrap("Home", "🏠")

st.title("JSE Stock Analyser")
st.caption(
    "A Koyfin-style screener for the Johannesburg Stock Exchange -- price data via Yahoo Finance (.JO tickers)."
)

universe = data.load_universe()

st.markdown(
    f"<span class='jse-pill'>{len(universe)} JSE-listed instruments tracked</span>"
    f"<span class='jse-pill'>{universe['gics_sector'].nunique()} GICS sectors</span>"
    f"<span class='jse-pill'>{universe['industry'].nunique()} industries</span>",
    unsafe_allow_html=True,
)

st.divider()

st.subheader("Market snapshot")
st.caption(
    "Loads recent price history for the largest JSE names to show today's movers. "
    "Full-market breadth (all 259 names) lives on the **Market Breadth** page."
)

top_n = st.slider("Number of largest-cap stocks to snapshot", 10, 60, 25, step=5)
snapshot_universe = universe.sort_values("market_cap_zar", ascending=False).head(top_n)

if st.button("Load snapshot", type="primary"):
    progress = st.progress(0.0, text="Fetching price data...")

    def _cb(done, total):
        progress.progress(done / total, text=f"Fetching price data... chunk {done}/{total}")

    hist = data.get_history_bulk(snapshot_universe["yf_ticker"].tolist(), period="1y", interval="1d", progress_cb=_cb)
    progress.empty()

    rows = []
    for _, r in snapshot_universe.iterrows():
        df = hist.get(r["yf_ticker"])
        if df is None or df.empty:
            continue
        last, pct = data.last_price_change(df)
        above200 = indicators.pct_above_sma(df, 200)
        rows.append(
            {
                "Symbol": r["symbol"],
                "Name": r["name"],
                "Sector": r["gics_sector"],
                "Last Close": last,
                "% Change": pct,
                "Above 200-SMA": "✅" if above200 else ("❌" if above200 is False else "—"),
                "Cap Tier": r["market_cap_tier"],
            }
        )

    if not rows:
        st.error(
            "No price data could be retrieved. If you're running this for the first time, "
            "check `python3 scripts/test_data_connection.py` to confirm Yahoo Finance is reachable."
        )
    else:
        snap_df = pd.DataFrame(rows).sort_values("% Change", ascending=False, na_position="last")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Top movers (up)**")
            st.dataframe(snap_df.head(10), hide_index=True, width="stretch")
        with c2:
            st.markdown("**Top movers (down)**")
            st.dataframe(snap_df.tail(10).sort_values("% Change"), hide_index=True, width="stretch")
        st.markdown("**Full snapshot**")
        st.dataframe(snap_df, hide_index=True, width="stretch")
else:
    st.info("Click **Load snapshot** to fetch live data (first load per session may take a few seconds).")

st.divider()

# --------------------------------------------------------------------------
# Market breadth summary -- always-on, so this page actually works as a
# "summary tab" rather than requiring a trip to the Market Breadth page.
# Uses the Mega/Large/Mid-cap subset (like that page's fast mode) and caches
# for 30 minutes so it doesn't refetch on every rerun.
# --------------------------------------------------------------------------
st.subheader("🌡️ Market breadth summary")
st.caption(
    "% of stocks trading above their 200-day SMA -- market-wide and by sector, for the Mega/Large/Mid-cap "
    "subset (for the full 259-stock scan, with more SMA options, see the **Market Breadth** page)."
)


@st.cache_data(ttl=1800, show_spinner=False)
def _home_breadth_summary():
    fast_universe = universe[universe["market_cap_tier"].isin(["Mega Cap", "Large Cap", "Mid Cap"])]
    hist = data.get_history_bulk(fast_universe["yf_ticker"].tolist(), period="18mo", interval="1d")
    rows = []
    for _, r in fast_universe.iterrows():
        df = hist.get(r["yf_ticker"])
        if df is None or df.empty or len(df) < 200:
            continue
        above = indicators.pct_above_sma(df, 200)
        if above is None:
            continue
        rows.append({"Sector": r["gics_sector"], "Above 200-SMA": above})
    return pd.DataFrame(rows)


with st.spinner("Computing market breadth (cached for 30 minutes)..."):
    breadth_df = _home_breadth_summary()

if breadth_df.empty:
    st.warning("Couldn't compute market breadth right now -- check `python3 scripts/test_data_connection.py`.")
else:
    total = len(breadth_df)
    above_count = int(breadth_df["Above 200-SMA"].sum())
    pct = above_count / total * 100 if total else 0

    col_gauge, col_bar = st.columns([1, 1.6])
    with col_gauge:
        st.metric("Stocks above 200-day SMA", f"{above_count} / {total}", f"{pct:.0f}%")
        fig_pie = px.pie(
            values=[above_count, total - above_count],
            names=["Above 200-SMA", "Below 200-SMA"],
            color_discrete_sequence=["#26A69A", "#EF5350"],
            hole=0.6,
        )
        fig_pie.update_layout(height=260, margin=dict(t=10, b=10), showlegend=True)
        st.plotly_chart(fig_pie, width="stretch")
    with col_bar:
        sector_breadth = (
            breadth_df.groupby("Sector")["Above 200-SMA"]
            .agg(Above="sum", Total="count")
            .assign(Pct=lambda d: (d["Above"] / d["Total"] * 100).round(1))
            .sort_values("Pct", ascending=False)
            .reset_index()
        )
        fig_bar = px.bar(
            sector_breadth,
            x="Pct",
            y="Sector",
            orientation="h",
            text=sector_breadth.apply(lambda r: f"{r['Above']}/{r['Total']} ({r['Pct']}%)", axis=1),
            color="Pct",
            color_continuous_scale=["#EF5350", "#8B93A7", "#26A69A"],
            range_color=[0, 100],
        )
        fig_bar.update_layout(height=380, coloraxis_showscale=False, xaxis_title="% above 200-SMA", yaxis_title="", margin=dict(t=10))
        st.plotly_chart(fig_bar, width="stretch")

st.divider()
st.subheader("Where to go next")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        "<div class='jse-card'><b>📊 Screener</b><br>Browse and filter all JSE stocks "
        "by market-cap tier, GICS sector, and industry.</div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        "<div class='jse-card'><b>📈 Charts</b><br>TradingView-style candlestick charts "
        "with SMAs, RSI, MACD and Bollinger Bands.</div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        "<div class='jse-card'><b>🌡️ Market Breadth</b><br>% of stocks above their 200-day SMA, "
        "market-wide and by sector.</div>",
        unsafe_allow_html=True,
    )
