import plotly.graph_objects as go
import streamlit as st

from src import data, indicators
from src import relative_performance as rp
from src.common import bootstrap
from src.theme import ACCENT, ACCENT_2, MUTED

bootstrap("Indices", "🧭")

st.title("🧭 JSE Indices")
st.markdown(
    "<div class='jse-card'>"
    "<b>What this is:</b> the same price / Average True Range % (ATRP) tools as the stock pages (ATR %, "
    "Stops &amp; Targets), but for a whole JSE index instead of a single stock -- e.g. to size a stop or "
    "target off the <b>Top 40</b> or <b>All Share</b> itself, or just to see how volatile a sector or "
    "industry has been as a whole."
    "<ul>"
    "<li>There's no single free official feed for most FTSE/JSE indices. Each one below is resolved "
    "against a short list of candidate Yahoo Finance tickers (see <code>BROAD_INDEX_CANDIDATES</code> / "
    "<code>SECTOR_INDEX_CANDIDATES</code> / <code>INDUSTRY_INDEX_CANDIDATES</code> in "
    "<code>src/relative_performance.py</code>) -- whichever one actually returns data on your machine is "
    "used, and the ticker is shown so you know exactly what you're looking at.</li>"
    "<li>Where none of an index's candidates work, or a sector/industry has no known index ticker at all, "
    "this falls back to a <b>constructed</b> index -- a market-cap-weighted blend of its own constituent "
    "stocks in this app's universe, starting at 100. That's a real, honestly-labelled proxy, but it's a "
    "<i>return</i> series, not a true price series, so ATR isn't available for it.</li>"
    "</ul></div>",
    unsafe_allow_html=True,
)
st.write("")

universe = data.load_universe()

# --------------------------------------------------------------------------
# Master index catalog -- every broad-market index this app knows a
# candidate ticker for, every GICS sector (even the ones with no known
# index ticker -- they just always fall back to constructed), and every
# industry this app knows a candidate ticker for.
# --------------------------------------------------------------------------
CATALOG = []  # (label, kind, candidates, key_name)
for _name, _candidates in rp.BROAD_INDEX_CANDIDATES.items():
    CATALOG.append((f"Broad market: {_name}", "broad", _candidates, _name))
for _sector in sorted(universe["gics_sector"].unique()):
    CATALOG.append((f"Sector: {_sector}", "sector", rp.SECTOR_INDEX_CANDIDATES.get(_sector, []), _sector))
for _industry, _candidates in rp.INDUSTRY_INDEX_CANDIDATES.items():
    CATALOG.append((f"Industry: {_industry}", "industry", _candidates, _industry))

catalog_labels = [c[0] for c in CATALOG]
_default_label = "Broad market: JSE Top 40"
default_index = catalog_labels.index(_default_label) if _default_label in catalog_labels else 0

c1, c2 = st.columns([2, 1])
with c1:
    choice = st.selectbox("Index", catalog_labels, index=default_index, key="idx_choice")
with c2:
    timeframe = st.selectbox(
        "Timeframe (for ATR)", ["Daily", "Weekly", "Monthly", "Quarterly"], index=0, key="idx_timeframe"
    )

_, kind, candidates, key_name = next(c for c in CATALOG if c[0] == choice)

# --------------------------------------------------------------------------
# Try a real Yahoo Finance price series first (needed for ATR); fall back
# to a constructed cap-weighted proxy if nothing resolves.
# --------------------------------------------------------------------------
raw, ticker_used = rp.resolve_index_ohlc(candidates) if candidates else (None, None)

if raw is not None:
    st.success(f"Real index data from Yahoo Finance: **{ticker_used}**")

    last_close, last_pct = data.last_price_change(raw)
    m1, m2, m3 = st.columns(3)
    m1.metric(
        f"{key_name} level", f"{last_close:,.2f}" if last_close is not None else "—",
        f"{last_pct:+.2f}%" if last_pct is not None else None,
    )
    m2.metric("Trading days of history", f"{len(raw):,}")
    m3.metric("Source ticker", ticker_used)

    st.divider()
    st.subheader(f"{key_name} price history")
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=raw.index, y=raw["Close"], mode="lines", line=dict(color=ACCENT, width=1.3)))
    fig_price.update_layout(height=320, yaxis_title="Index level", xaxis_title="")
    st.plotly_chart(fig_price, width="stretch")

    df = raw if timeframe == "Daily" else data.resample_ohlc(
        raw, {"Weekly": "W", "Monthly": "M", "Quarterly": "Q"}[timeframe]
    )
    trp = indicators.true_range_pct(df).dropna()
    if trp.empty:
        st.warning("Not enough data at this timeframe to compute True Range %.")
    else:
        horizons = indicators.ATRP_HORIZONS[timeframe]
        atrp_table = indicators.average_true_range_pct(df, horizons)

        one_year_row = atrp_table[atrp_table["Horizon"] == "1 Year"]
        if one_year_row.empty or one_year_row["Avg True Range %"].isna().all():
            fallback = atrp_table.dropna(subset=["Avg True Range %"])
            headline_label = fallback.iloc[0]["Horizon"] if not fallback.empty else "—"
            headline_val = fallback.iloc[0]["Avg True Range %"] if not fallback.empty else None
        else:
            headline_label = "1 Year"
            headline_val = one_year_row["Avg True Range %"].iloc[0]

        st.divider()
        hm1, hm2, hm3 = st.columns(3)
        hm1.metric("Latest True Range %", f"{trp.iloc[-1]:.2%}")
        hm2.metric(
            f"{headline_label} avg True Range %",
            f"{headline_val:.2%}" if headline_val == headline_val and headline_val is not None else "—",
        )
        hm3.metric(f"{timeframe} bars used", f"{len(df):,}")

        col1, col2 = st.columns([1.1, 1])
        with col1:
            st.subheader("Average True Range % by horizon")
            disp = atrp_table.copy()
            disp["Avg True Range %"] = disp["Avg True Range %"].map(lambda x: f"{x:.3%}" if x == x else "—")
            st.dataframe(disp, hide_index=True, width="stretch")

            fig_atrp = go.Figure()
            plot_df = atrp_table.dropna(subset=["Avg True Range %"])
            fig_atrp.add_trace(go.Bar(x=plot_df["Horizon"], y=plot_df["Avg True Range %"], marker_color=ACCENT, name="Avg TR%"))
            fig_atrp.update_layout(height=360, yaxis_tickformat=".2%", yaxis_title="Avg True Range %", xaxis_title="")
            st.plotly_chart(fig_atrp, width="stretch")
        with col2:
            st.subheader(f"{timeframe} True Range % over time")
            recent = trp.tail(min(len(trp), 500))
            fig_trp = go.Figure()
            fig_trp.add_trace(go.Scatter(x=recent.index, y=recent, mode="lines", line=dict(color=ACCENT_2, width=1.2), name="TR%"))
            fig_trp.add_hline(y=trp.mean(), line_dash="dot", line_color=MUTED, annotation_text="Full-history mean")
            fig_trp.update_layout(height=360, yaxis_tickformat=".2%", yaxis_title="True Range %", xaxis_title="")
            st.plotly_chart(fig_trp, width="stretch")

        st.caption(
            "\"Periods Available\" below the requested horizon means there isn't enough history yet to fill "
            "that window -- the average is computed over whatever is available instead of blowing up."
        )

else:
    if candidates:
        st.warning(
            f"None of this index's candidate Yahoo Finance tickers ({', '.join(candidates)}) returned "
            "data on this machine -- showing a constructed version built from its own constituents "
            "instead. Run `python3 scripts/test_data_connection.py` to see which candidates work for "
            "you, and edit the candidate list in `src/relative_performance.py` if you find a working one."
        )
    else:
        st.info(
            f"No known Yahoo Finance index ticker for **{key_name}** -- showing a constructed version "
            "built from its own constituents in this app's universe instead."
        )

    if kind == "broad":
        subset = rp.BROAD_FALLBACK.get(key_name, lambda uni: uni)(universe)
    elif kind == "sector":
        subset = universe[universe["gics_sector"] == key_name]
    else:
        subset = universe[universe["industry"] == key_name]

    if subset.empty:
        st.error("No constituents found for this index in the current universe.")
        st.stop()

    with st.spinner(f"Building a constructed index from {len(subset)} constituent(s)..."):
        tickers = subset["yf_ticker"].tolist()
        hist = data.get_history_bulk(tickers, period="5y", interval="1d")
        series = rp.cap_weighted_index(hist, subset)

    if series is None or series.empty:
        st.error("Couldn't build a constructed index -- no usable price history for its constituents.")
    else:
        st.divider()
        pct_total = (series.iloc[-1] / series.iloc[0] - 1) * 100 if series.iloc[0] else None
        cm1, cm2, cm3 = st.columns(3)
        cm1.metric(f"Constructed {key_name} level (start = 100)", f"{series.iloc[-1]:,.1f}")
        cm2.metric("Change over shown period", f"{pct_total:+.1f}%" if pct_total is not None else "—")
        cm3.metric("Constituents used", len(tickers))
        st.caption(
            "Market-cap-weighted blend of the constituents' own daily returns, compounded from a base of "
            "100 -- not an official index level, and no True Range % / ATR is shown since there's no "
            "single real price series behind it."
        )

        fig_constructed = go.Figure()
        fig_constructed.add_trace(go.Scatter(x=series.index, y=series, mode="lines", line=dict(color=ACCENT_2, width=1.3)))
        fig_constructed.update_layout(height=360, yaxis_title="Index level (start = 100)", xaxis_title="")
        st.plotly_chart(fig_constructed, width="stretch")
