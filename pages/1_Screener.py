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
# Tab 2: market-cap decomposition tree -- a ranked, uniform-height bar list
# per level (src.treeviz.drilldown_bar_figure), in a single accent colour
# with a light "track" behind every bar. Click a bar to drill into it; a
# new panel appears below showing that branch's own breakdown, exactly like
# expanding a branch in a Power-BI decomposition tree. This replaced an
# earlier Icicle-chart version that didn't hold up: Icicle's tile *area* is
# proportional to value, which gave wildly uneven row heights (some tiles
# unreadable slivers) and arbitrary per-branch colours, neither of which
# matched the clean single-colour ranked-bar look of the reference image.
# --------------------------------------------------------------------------
with tab_tree:
    st.caption(
        "Click a bar to drill into it -- each click reveals that branch's own breakdown below. "
        "Change \"Decompose by\" or hit ↺ Reset to start over."
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
        dim_label = {"gics_sector": "sector", "industry": "industry", "market_cap_tier": "cap tier"}
        MAX_BARS = 25  # per level, so a level with many categories stays readable

        top_row, reset_row = st.columns([5, 1])
        with top_row:
            path_choice = st.selectbox("Decompose by", list(path_options.keys()), key="tree_path_choice")
        path = path_options[path_choice]

        # A new "decompose by" path invalidates any drill-down made under the
        # old one (e.g. a selected industry doesn't mean anything once you've
        # switched to grouping by cap tier), so clear it rather than risk
        # showing a stale, mismatched branch.
        if st.session_state.get("tree_path_prev") != path_choice:
            st.session_state["tree_sel1"] = None
            st.session_state["tree_sel2"] = None
            st.session_state["tree_path_prev"] = path_choice

        with reset_row:
            st.write("")  # vertical nudge to roughly align with the selectbox
            if st.button("↺ Reset", key="tree_reset_btn", disabled=not st.session_state.get("tree_sel1")):
                st.session_state["tree_sel1"] = None
                st.session_state["tree_sel2"] = None

        sel1 = st.session_state.get("tree_sel1")
        sel2 = st.session_state.get("tree_sel2") if len(path) > 1 else None
        crumbs = [f"JSE ({len(filtered)} stocks)"]
        if sel1:
            crumbs.append(sel1)
        if sel2:
            crumbs.append(sel2)
        st.markdown(" → ".join(f"**{c}**" for c in crumbs))

        # --- Level 1: every filtered stock, grouped by the first dimension ---
        labels1, values1, omitted1 = treeviz.ranked_groups(filtered, path[0], "market_cap_zar", MAX_BARS)
        st.caption(f"By {dim_label.get(path[0], path[0])} (market cap):")
        fig1 = treeviz.drilldown_bar_figure(labels1, values1, [treeviz.format_rand(v) for v in values1])
        event1 = st.plotly_chart(fig1, width="stretch", on_select="rerun", selection_mode="points", key="tree_chart_lvl1")
        if omitted1:
            st.caption(f"+ {omitted1} smaller {dim_label.get(path[0], path[0])}(s) not shown -- refine your filters to see them.")

        clicked1 = treeviz.clicked_bar_label(event1)
        if clicked1 is not None and clicked1 in labels1 and clicked1 != sel1:
            sel1 = clicked1
            st.session_state["tree_sel1"] = sel1
            st.session_state["tree_sel2"] = None
            sel2 = None
        elif sel1 is not None and sel1 not in labels1:
            # The underlying filters changed since this was selected (e.g. the
            # chosen sector was filtered out) -- self-heal instead of crashing.
            sel1 = None
            st.session_state["tree_sel1"] = None
            st.session_state["tree_sel2"] = None
            sel2 = None

        # --- Level 2: everything under the selected level-1 branch ---
        if sel1 is not None:
            scope1 = filtered[filtered[path[0]].astype(str) == sel1]
            st.divider()
            if len(path) > 1:
                labels2, values2, omitted2 = treeviz.ranked_groups(scope1, path[1], "market_cap_zar", MAX_BARS)
                st.caption(f"**{sel1}**, by {dim_label.get(path[1], path[1])} (market cap):")
                fig2 = treeviz.drilldown_bar_figure(labels2, values2, [treeviz.format_rand(v) for v in values2])
                event2 = st.plotly_chart(
                    fig2, width="stretch", on_select="rerun", selection_mode="points", key="tree_chart_lvl2"
                )
                if omitted2:
                    st.caption(f"+ {omitted2} smaller {dim_label.get(path[1], path[1])}(s) not shown here.")

                clicked2 = treeviz.clicked_bar_label(event2)
                if clicked2 is not None and clicked2 in labels2 and clicked2 != sel2:
                    sel2 = clicked2
                    st.session_state["tree_sel2"] = sel2
                elif sel2 is not None and sel2 not in labels2:
                    sel2 = None
                    st.session_state["tree_sel2"] = None

                # --- Level 3: individual stocks under the level-2 branch ---
                if sel2 is not None:
                    scope2 = scope1[scope1[path[1]].astype(str) == sel2]
                    st.divider()
                    labels3, values3, omitted3 = treeviz.ranked_groups(scope2, "symbol", "market_cap_zar", MAX_BARS)
                    st.caption(f"**{sel1} → {sel2}**, individual stocks:")
                    fig3 = treeviz.drilldown_bar_figure(labels3, values3, [treeviz.format_rand(v) for v in values3])
                    st.plotly_chart(fig3, width="stretch", key="tree_chart_lvl3")
                    if omitted3:
                        st.caption(f"+ {omitted3} smaller stock(s) not shown here -- see the Table tab for the full list.")
            else:
                # Single-dimension path (e.g. "Industry → Stock"): level 2 is
                # already the individual stocks, no further drill needed.
                labels2, values2, omitted2 = treeviz.ranked_groups(scope1, "symbol", "market_cap_zar", MAX_BARS)
                st.caption(f"**{sel1}**, individual stocks:")
                fig2 = treeviz.drilldown_bar_figure(labels2, values2, [treeviz.format_rand(v) for v in values2])
                st.plotly_chart(fig2, width="stretch", key="tree_chart_lvl2_leaf")
                if omitted2:
                    st.caption(f"+ {omitted2} smaller stock(s) not shown here -- see the Table tab for the full list.")

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
