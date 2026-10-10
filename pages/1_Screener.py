import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src import data, indicators, treeviz
from src.common import bootstrap
from src.theme import BORDER, DOWN, PANEL_2, UP

bootstrap("Screener", "📊")

st.title("📊 Stock Screener")
st.caption("Group and filter the full JSE universe by market-cap tier, GICS sector, and industry.")

universe = data.load_universe()

# --------------------------------------------------------------------------
# Filters -- shared by all three tabs below
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

tab_table, tab_tree, tab_map = st.tabs(["📋 Table", "🌳 Market Cap Breakdown", "🗺️ Performance Map"])

# --------------------------------------------------------------------------
# Tab 1: the original filterable/groupable table, unchanged
# --------------------------------------------------------------------------
with tab_table:
    group_by = st.radio("Group by", ["None", "Market-cap tier", "GICS sector", "Industry"], horizontal=True, key="screener_group_by")

    pull_live = st.checkbox(
        "Pull live price / % change / SMA signal for the filtered rows",
        value=len(filtered) <= 60,
        help="Fetches 1y of price history for every row shown. Uncheck for large lists to keep it fast.",
        key="screener_pull_live",
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

        # Shared with the Performance Map tab below, so switching tabs after
        # pulling live data here doesn't force a second fetch of the same
        # tickers -- see the cache-key check in tab_map.
        st.session_state["screener_live_pulled"] = {
            "tickers": tuple(sorted(filtered["yf_ticker"].tolist())),
            "pct_by_ticker": dict(zip(filtered["yf_ticker"], pct_changes)),
        }

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

# --------------------------------------------------------------------------
# Tab 2: market-cap decomposition tree -- an Icicle chart (Plotly's closest
# native equivalent to a Power-BI-style decomposition tree: click any tile
# to drill into it, click the root/breadcrumb to zoom back out, no custom
# JS needed). You choose which dimension it decomposes by second, after
# sector -- that's the "decompose by X" interaction this is standing in for.
# --------------------------------------------------------------------------
with tab_tree:
    st.caption(
        "Box size = market cap. Click any sector (or tier) to drill into it; click the root label on "
        "the left, or a tile's own breadcrumb, to zoom back out."
    )
    if filtered.empty:
        st.info("No stocks match your filters.")
    else:
        path_options = {
            "Sector → Industry → Stock": ["gics_sector", "industry"],
            "Sector → Cap Tier → Stock": ["gics_sector", "market_cap_tier"],
            "Cap Tier → Sector → Stock": ["market_cap_tier", "gics_sector"],
            "Industry → Stock": ["industry"],
        }
        path_choice = st.selectbox("Decompose by", list(path_options.keys()), key="tree_path_choice")
        path = path_options[path_choice]

        hier = treeviz.build_hierarchy(
            filtered,
            path=path,
            leaf_id_col="symbol",
            leaf_label_col="symbol",
            value_col="market_cap_zar",
            root_label=f"JSE ({len(filtered)} stocks)",
        )
        node_text = [treeviz.format_rand(v) for v in hier["values"]]

        fig_tree = go.Figure(go.Icicle(
            ids=hier["ids"],
            labels=hier["labels"],
            parents=hier["parents"],
            values=hier["values"],
            branchvalues="total",
            tiling=dict(orientation="h"),
            text=node_text,
            texttemplate="<b>%{label}</b><br>%{text}",
            hovertemplate="%{label}<br>%{text}<br>%{percentParent:.1%} of parent<extra></extra>",
            maxdepth=len(path) + 1,  # root + each chosen level; stock leaves reveal on drill-in
            root=dict(color=PANEL_2),
            marker=dict(line=dict(width=1, color=BORDER)),
        ))
        fig_tree.update_layout(height=580, margin=dict(t=10, l=10, r=10, b=10), font=dict(size=13))
        st.plotly_chart(fig_tree, width="stretch")

# --------------------------------------------------------------------------
# Tab 3: performance treemap -- Sector > Industry > Stock, sized by market
# cap, coloured by today's % move (market-cap-weighted average rolling up
# through industry and sector), in the style of a Finviz/market-map heatmap.
# --------------------------------------------------------------------------
with tab_map:
    st.caption(
        "Box size = market cap, colour = today's % move (sectors/industries show the market-cap-"
        "weighted average of their constituents). Click a tile to drill in, same as the tree above."
    )
    if filtered.empty:
        st.info("No stocks match your filters.")
    else:
        cached = st.session_state.get("screener_live_pulled")
        cache_key = tuple(sorted(filtered["yf_ticker"].tolist()))
        has_cached = cached is not None and cached["tickers"] == cache_key

        load_clicked = st.button(
            "🔄 Load / refresh performance map" if not has_cached else "🔄 Refresh performance map",
            key="map_load_btn",
        )

        if load_clicked or has_cached:
            if load_clicked or not has_cached:
                progress = st.progress(0.0, text="Fetching price data...")

                def _cb2(done, total):
                    progress.progress(done / total, text=f"Fetching price data... chunk {done}/{total}")

                hist = data.get_history_bulk(
                    filtered["yf_ticker"].tolist(), period="5d", interval="1d", progress_cb=_cb2
                )
                progress.empty()
                pct_by_ticker = {}
                for t in filtered["yf_ticker"]:
                    df = hist.get(t)
                    if df is None or df.empty:
                        pct_by_ticker[t] = None
                        continue
                    _, pct = data.last_price_change(df)
                    pct_by_ticker[t] = pct
                st.session_state["screener_live_pulled"] = {"tickers": cache_key, "pct_by_ticker": pct_by_ticker}
            else:
                pct_by_ticker = cached["pct_by_ticker"]

            map_df = filtered.copy()
            map_df["pct_change"] = map_df["yf_ticker"].map(pct_by_ticker)
            n_missing = map_df["pct_change"].isna().sum()

            hier = treeviz.build_hierarchy(
                map_df,
                path=["gics_sector", "industry"],
                leaf_id_col="symbol",
                leaf_label_col="symbol",
                value_col="market_cap_zar",
                color_col="pct_change",
                root_label=f"JSE ({len(map_df)} stocks)",
            )
            node_text = [
                f"{c:+.2f}%" if c is not None and c == c else "—" for c in hier["colors"]
            ]
            colors = [c if c is not None else np.nan for c in hier["colors"]]

            fig_map = go.Figure(go.Treemap(
                ids=hier["ids"],
                labels=hier["labels"],
                parents=hier["parents"],
                values=hier["values"],
                branchvalues="total",
                text=node_text,
                texttemplate="<b>%{label}</b><br>%{text}",
                hovertemplate="%{label}<br>%{text}<br>mkt cap %{value:,.0f}<extra></extra>",
                marker=dict(
                    colors=colors,
                    colorscale=[[0, DOWN], [0.5, "#1A1F2B"], [1, UP]],
                    cmid=0,
                    line=dict(width=1, color=BORDER),
                    colorbar=dict(title="% chg", ticksuffix="%"),
                ),
                root=dict(color=PANEL_2),
            ))
            fig_map.update_layout(height=580, margin=dict(t=10, l=10, r=10, b=10), font=dict(size=13))
            st.plotly_chart(fig_map, width="stretch")
            if n_missing:
                st.caption(f"{n_missing} of {len(map_df)} stocks had no recent price data and show as neutral/blank tiles.")
        else:
            st.info(
                "Click **Load / refresh performance map** to fetch the latest prices for the "
                f"{len(filtered)} filtered stocks and build the map."
            )
