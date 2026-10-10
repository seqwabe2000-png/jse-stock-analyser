import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data, indicators, instruments, pairs
from src import position_sizing as ps
from src.common import bootstrap
from src.theme import ACCENT, ACCENT_2, DOWN, MUTED, UP
from src.ui import percentile_grid_html

bootstrap("Stops & Targets", "🎯")

st.title("🎯 Stops & Targets")
st.markdown(
    "<div class='jse-card'>"
    "<b>What this tool does:</b> works out sensible stop-loss and take-profit levels for a single-stock "
    "or pairs trade, using two independent methods, so you can see the <b>odds</b> behind each level "
    "rather than just guessing a round number."
    "<ul>"
    "<li><b>DoR method</b> (reproduces <code>DoR_Stops_and_Targets.xlsx</code>): looks at the stock's own "
    "historical return distribution and picks a stop at a chosen percentile of the downside -- so you "
    "know upfront roughly how often a move that size has actually happened before.</li>"
    "<li><b>ATRP method</b> (reproduces <code>ATRP_Stops_and_Targets.xlsx</code>): uses long-term average "
    "weekly volatility (True Range %) for the stop and long-term average quarterly volatility for the "
    "target -- a slower-moving, volatility-based alternative to the percentile approach.</li>"
    "</ul>"
    "Both methods let you set your own risk:reward ratio -- not investment advice.</div>",
    unsafe_allow_html=True,
)
st.write("")

universe = instruments.with_indices(data.load_universe())
label_to_row = {f"{r['symbol']} — {r['name']}": r for _, r in universe.iterrows()}
labels = sorted(label_to_row.keys())

RESAMPLE = {"Daily": None, "Weekly": "W", "Monthly": "M"}


def _hist(row, period="max"):
    # Indices with no real OHLC ticker (only a constructed-proxy return
    # series -- see src/instruments.py) aren't offered in this picker at
    # all, since the ATRP tab below needs real High/Low, which only a
    # genuine price series can give.
    return instruments.get_history_for_row(row, period=period, interval="1d")


# --------------------------------------------------------------------------
# Step 1 -- trade setup
# --------------------------------------------------------------------------
st.subheader("① Trade setup")
trade_type = st.radio("Trade type", ["Single stock", "Pairs trade (spread)"], horizontal=True, key="st_trade_type")

if trade_type == "Single stock":
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        choice = st.selectbox("Stock / index", options=labels, key="st_single_stock")
        row = label_to_row[choice]
    with c2:
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True, key="st_direction")
    with c3:
        history_period = st.selectbox("History", ["5y", "10y", "max"], index=1, key="st_history")

    with st.spinner(f"Fetching {row['symbol']}'s price history..."):
        raw = _hist(row, history_period)
    if raw.empty:
        st.error(f"No price data available for {row['symbol']}.")
        st.stop()
    entry_price = raw["Close"].iloc[-1]
    last_change, last_pct = data.last_price_change(raw)
    pm1, pm2 = st.columns([1, 3])
    pm1.metric(
        f"{row['symbol']} current price",
        f"{entry_price:,.2f}",
        f"{last_pct:+.2f}%" if last_pct is not None else None,
    )
    pm2.caption(f"This is used as the entry price for the stop/target calculations below ({direction.lower()} trade).")
else:
    c1, c2 = st.columns(2)
    with c1:
        label_long = st.selectbox("Long leg (stock / index A)", labels, index=0, key="st_long")
    with c2:
        default_short_idx = 1 if len(labels) > 1 else 0
        label_short = st.selectbox(
            "Short leg (stock / index B)", labels, index=default_short_idx, key="st_short",
            help="For an index hedge, pick the index here (e.g. the Top 40 or All Share).",
        )
    row_long, row_short = label_to_row[label_long], label_to_row[label_short]

    if row_long["yf_ticker"] == row_short["yf_ticker"]:
        st.warning("Pick two different stocks for a pairs trade.")
        st.stop()

    c3, c4, c5 = st.columns(3)
    with c3:
        long_exposure = st.number_input("Long gross exposure (R)", min_value=0.0, value=100_000.0, step=5_000.0, key="st_long_exp")
    with c4:
        short_exposure = st.number_input("Short gross exposure (R)", min_value=0.0, value=100_000.0, step=5_000.0, key="st_short_exp")
    with c5:
        history_period = st.selectbox("History", ["5y", "10y", "max"], index=1, key="st_history_pairs")

    total_exposure = long_exposure + short_exposure
    if total_exposure <= 0:
        st.warning("Enter at least one non-zero gross exposure.")
        st.stop()
    weight_long, weight_short = long_exposure / total_exposure, short_exposure / total_exposure

    with st.spinner("Fetching price history for both legs..."):
        raw_long = _hist(row_long, history_period)
        raw_short = _hist(row_short, history_period)
    if raw_long.empty or raw_short.empty:
        st.error("Couldn't get price data for one or both legs.")
        st.stop()
    price_long, price_short = raw_long["Close"].iloc[-1], raw_short["Close"].iloc[-1]
    chg_long, pct_long = data.last_price_change(raw_long)
    chg_short, pct_short = data.last_price_change(raw_short)
    pm1, pm2 = st.columns(2)
    pm1.metric(f"{row_long['symbol']} current price (long)", f"{price_long:,.2f}", f"{pct_long:+.2f}%" if pct_long is not None else None)
    pm2.metric(f"{row_short['symbol']} current price (short)", f"{price_short:,.2f}", f"{pct_short:+.2f}%" if pct_short is not None else None)
    st.caption(
        f"Long {weight_long:.0%} {row_long['symbol']} / Short {weight_short:.0%} {row_short['symbol']} "
        f"(gross exposure R{total_exposure:,.0f}). Spread return = {weight_long:.2f}×{row_long['symbol']}'s "
        f"return − {weight_short:.2f}×{row_short['symbol']}'s return; positive means the trade made money."
    )

st.divider()

# --------------------------------------------------------------------------
# Step 2 -- method tabs
# --------------------------------------------------------------------------
st.subheader("② Pick a tool")
tab_dor, tab_atrp, tab_beta = st.tabs(
    ["📊 DoR method (percentile-based)", "📈 ATRP method (volatility-based)", "⚖️ Beta-Neutral Sizing"]
)

# ==========================================================================
# DoR method
# ==========================================================================
with tab_dor:
    frequency = st.selectbox(
        "Return frequency", ["Daily", "Weekly", "Monthly"], index=2, key="st_dor_freq",
        help="DoR_Stops_and_Targets.xlsx uses monthly returns -- daily/weekly are also supported here.",
    )
    resample_freq = RESAMPLE[frequency]

    if trade_type == "Single stock":
        df_freq = raw if resample_freq is None else data.resample_ohlc(raw, resample_freq)
        series = indicators.compute_returns(df_freq)["C-C Return"].dropna()
    else:
        df_long_freq = raw_long if resample_freq is None else data.resample_ohlc(raw_long, resample_freq)
        df_short_freq = raw_short if resample_freq is None else data.resample_ohlc(raw_short, resample_freq)
        ret_long = indicators.compute_returns(df_long_freq)["C-C Return"]
        ret_short = indicators.compute_returns(df_short_freq)["C-C Return"]
        series = pairs.spread_returns(ret_long, ret_short, weight_long, weight_short).dropna()

    if len(series) < 20:
        st.warning(f"Only {len(series)} {frequency.lower()} periods available -- results below will be unreliable.")

    if series.empty:
        st.error("Not enough overlapping return history to compute a distribution.")
    else:
        pct_table = indicators.percentile_table(series)

        c1, c2 = st.columns([1, 1])
        with c1:
            stop_percentile = st.slider(
                "Stop percentile (worst-case tail)", 1, 49, 10, key="st_dor_pctile",
                help="A stop at the 10th percentile means, historically, about 10% of periods moved against "
                "you by at least this much.",
            )
        with c2:
            rr_dor = st.number_input(
                "Risk : Reward ratio (Target ÷ Stop)", min_value=0.5, max_value=10.0, value=3.0, step=0.5,
                key="st_dor_rr", help="DoR_Stops_and_Targets.xlsx assumed a fixed 3:1 -- set your own here.",
            )

        stop_value = float(np.percentile(series, stop_percentile))
        stop_pct = abs(stop_value)
        target_pct = stop_pct * rr_dor

        stop_odds = (series <= -stop_pct).mean() * 100
        target_odds = (series >= target_pct).mean() * 100

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Stop %", f"{stop_pct:.2%}")
        m2.metric("Target %", f"{target_pct:.2%}")
        m3.metric("Odds of hitting stop", f"~{stop_odds:.1f}%")
        m4.metric("Odds of hitting target", f"~{target_odds:.1f}%")
        st.caption(
            f"\"Odds\" are the historical frequency of a single {frequency.lower()} period moving at least "
            "that far in the adverse (stop) or favourable (target) direction -- an empirical estimate, not a guarantee."
        )

        if trade_type == "Single stock":
            if direction == "Long":
                stop_price, target_price = entry_price * (1 - stop_pct), entry_price * (1 + target_pct)
            else:
                stop_price, target_price = entry_price * (1 + stop_pct), entry_price * (1 - target_pct)
            p1, p2, p3 = st.columns(3)
            p1.metric("Entry price", f"{entry_price:,.2f}")
            p2.metric("Stop price", f"{stop_price:,.2f}")
            p3.metric("Target price", f"{target_price:,.2f}")
        else:
            dollar_stop = -stop_pct * total_exposure
            dollar_target = target_pct * total_exposure
            p1, p2 = st.columns(2)
            p1.metric("$ Stop loss", f"R{dollar_stop:,.0f}")
            p2.metric("$ Target profit", f"R{dollar_target:,.0f}")

        with st.expander("Full percentile table (1st–99th)"):
            st.markdown(percentile_grid_html(pct_table), unsafe_allow_html=True)

        fig = go.Figure()
        colors = [DOWN if v < 0 else UP for v in series]
        fig.add_trace(go.Bar(x=series.index, y=series.values, marker_color=colors, name=f"{frequency} return"))
        fig.add_hline(y=-stop_pct, line_dash="dash", line_color=DOWN, annotation_text="Stop", annotation_position="right")
        fig.add_hline(y=target_pct, line_dash="dash", line_color=UP, annotation_text="Target", annotation_position="right")
        fig.update_layout(height=360, yaxis_tickformat=".1%", yaxis_title=f"{frequency} return", showlegend=False)
        st.plotly_chart(fig, width="stretch")

# ==========================================================================
# ATRP method
# ==========================================================================
with tab_atrp:
    st.caption(
        "Stop is based on long-term **weekly** average True Range % (volatility of the weekly range); "
        "target is based on long-term **quarterly** average True Range % -- regardless of the frequency "
        "chosen on the DoR tab."
    )

    if trade_type == "Single stock":
        weekly_df = data.resample_ohlc(raw, "W")
        quarterly_df = data.resample_ohlc(raw, "Q")
        weekly_horizons = indicators.ATRP_HORIZONS["Weekly"]
        quarterly_horizons = indicators.ATRP_HORIZONS["Quarterly"]
        atrp_weekly = indicators.average_true_range_pct(weekly_df, weekly_horizons)
        atrp_quarterly = indicators.average_true_range_pct(quarterly_df, quarterly_horizons)
        trp_weekly_series = indicators.true_range_pct(weekly_df).dropna()
    else:
        weekly_long, weekly_short = data.resample_ohlc(raw_long, "W"), data.resample_ohlc(raw_short, "W")
        quarterly_long, quarterly_short = data.resample_ohlc(raw_long, "Q"), data.resample_ohlc(raw_short, "Q")
        weekly_horizons = indicators.ATRP_HORIZONS["Weekly"]
        quarterly_horizons = indicators.ATRP_HORIZONS["Quarterly"]
        atrp_weekly_long = indicators.average_true_range_pct(weekly_long, weekly_horizons)
        atrp_weekly_short = indicators.average_true_range_pct(weekly_short, weekly_horizons)
        atrp_quarterly_long = indicators.average_true_range_pct(quarterly_long, quarterly_horizons)
        atrp_quarterly_short = indicators.average_true_range_pct(quarterly_short, quarterly_horizons)
        st.caption(
            "For a pairs trade, each leg's ATRP is blended by its share of gross exposure -- a simplification "
            "(there's no single official ATRP for a two-leg spread), shown for context alongside the DoR "
            "spread-return method above, which is the more rigorous of the two for a pairs trade."
        )

    weekly_labels = [h[0] for h in weekly_horizons]
    quarterly_labels = [h[0] for h in quarterly_horizons]

    c1, c2 = st.columns(2)
    with c1:
        stop_horizon = st.selectbox("Stop horizon (weekly ATRP)", weekly_labels, index=len(weekly_labels) - 1, key="st_atrp_stop_h")
    with c2:
        use_custom_rr = st.checkbox("Override target with a custom risk:reward ratio", key="st_atrp_custom_rr")

    def _lookup(table, label):
        row = table[table["Horizon"] == label]
        if row.empty or row["Avg True Range %"].isna().all():
            return None
        return float(row["Avg True Range %"].iloc[0])

    if trade_type == "Single stock":
        stop_pct_atrp = _lookup(atrp_weekly, stop_horizon)
    else:
        v_long, v_short = _lookup(atrp_weekly_long, stop_horizon), _lookup(atrp_weekly_short, stop_horizon)
        stop_pct_atrp = (
            v_long * weight_long + v_short * weight_short if v_long is not None and v_short is not None else None
        )

    if stop_pct_atrp is None:
        st.warning(f"Not enough weekly history to compute the {stop_horizon} ATRP yet -- try a shorter horizon.")
    else:
        if use_custom_rr:
            rr_atrp = st.number_input(
                "Risk : Reward ratio (Target ÷ Stop)", min_value=0.5, max_value=10.0, value=2.0, step=0.5, key="st_atrp_rr"
            )
            target_pct_atrp = stop_pct_atrp * rr_atrp
            target_source = f"{rr_atrp:.1f}:1 of the weekly ATRP stop"
        else:
            target_horizon = st.selectbox(
                "Target horizon (quarterly ATRP)", quarterly_labels, index=len(quarterly_labels) - 1, key="st_atrp_target_h"
            )
            if trade_type == "Single stock":
                target_pct_atrp = _lookup(atrp_quarterly, target_horizon)
            else:
                tv_long, tv_short = _lookup(atrp_quarterly_long, target_horizon), _lookup(atrp_quarterly_short, target_horizon)
                target_pct_atrp = (
                    tv_long * weight_long + tv_short * weight_short
                    if tv_long is not None and tv_short is not None else None
                )
            target_source = f"{target_horizon} quarterly ATRP"

        if target_pct_atrp is None:
            st.warning("Not enough quarterly history to compute that target horizon yet -- try a shorter one, or tick the custom risk:reward override above.")
        else:
            implied_rr = target_pct_atrp / stop_pct_atrp if stop_pct_atrp else None
            m1, m2, m3 = st.columns(3)
            m1.metric("Stop % (weekly ATRP)", f"{stop_pct_atrp:.2%}")
            m2.metric(f"Target % ({target_source})", f"{target_pct_atrp:.2%}")
            m3.metric("Implied risk:reward", f"{implied_rr:.2f} : 1" if implied_rr else "—")

            if trade_type == "Single stock":
                if direction == "Long":
                    stop_price_a, target_price_a = entry_price * (1 - stop_pct_atrp), entry_price * (1 + target_pct_atrp)
                else:
                    stop_price_a, target_price_a = entry_price * (1 + stop_pct_atrp), entry_price * (1 - target_pct_atrp)
                p1, p2, p3 = st.columns(3)
                p1.metric("Entry price", f"{entry_price:,.2f}")
                p2.metric("Stop price", f"{stop_price_a:,.2f}")
                p3.metric("Target price", f"{target_price_a:,.2f}")
                odds_stop = (trp_weekly_series >= stop_pct_atrp).mean() * 100 if not trp_weekly_series.empty else None
                if odds_stop is not None:
                    st.caption(
                        f"Historically, a single week's True Range % has exceeded this stop distance about "
                        f"{odds_stop:.1f}% of the time -- a rough proxy for how often a week this volatile occurs."
                    )
            else:
                dollar_stop_a = -stop_pct_atrp * total_exposure
                dollar_target_a = target_pct_atrp * total_exposure
                p1, p2 = st.columns(2)
                p1.metric("$ Stop loss", f"R{dollar_stop_a:,.0f}")
                p2.metric("$ Target profit", f"R{dollar_target_a:,.0f}")

            with st.expander("Full weekly ATRP (stop) and quarterly ATRP (target) tables"):
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.markdown("**Weekly ATRP (stop basis)**")
                    disp = (atrp_weekly if trade_type == "Single stock" else atrp_weekly_long).copy()
                    disp["Avg True Range %"] = disp["Avg True Range %"].map(lambda x: f"{x:.3%}" if x == x else "—")
                    st.dataframe(disp, hide_index=True, width="stretch")
                with cc2:
                    st.markdown("**Quarterly ATRP (target basis)**")
                    disp2 = (atrp_quarterly if trade_type == "Single stock" else atrp_quarterly_long).copy()
                    disp2["Avg True Range %"] = disp2["Avg True Range %"].map(lambda x: f"{x:.3%}" if x == x else "—")
                    st.dataframe(disp2, hide_index=True, width="stretch")

# ==========================================================================
# Beta-Neutral Sizing (reproduces beta_neutral_template.xlsx)
# ==========================================================================
with tab_beta:
    st.caption(
        "Sizes a long basket against a short basket so that beta-weighted dollars match on both sides -- "
        "removing market risk, not sector/style/single-stock risk. **Pair-by-Pair** auto-fills its first row "
        "from the stock/pair chosen in step ① above (beta estimated automatically -- see below); **Basket "
        "Calculator** is self-contained, since a basket's many stocks don't map onto a single step ① "
        "selection -- enter its tickers and betas directly. Betas can also always be overridden/typed by "
        "hand: the slope of a regression of the stock's returns on an index's returns (e.g. weekly or daily "
        "over 2-5 years against the JSE All Share), or a figure from a data provider. Costs (borrow, "
        "financing, margin, spreads, rebalancing) aren't modelled. General calculation aid, not investment advice."
    )

    @st.cache_data(ttl=3600, show_spinner=False)
    def _bn_benchmark_returns(period):
        bench_raw = data.get_history(data.BENCHMARKS["JSE All Share"], period=period, interval="1d")
        if bench_raw is None or bench_raw.empty:
            return pd.Series(dtype=float)
        return indicators.compute_returns(bench_raw)["C-C Return"]

    def _bn_auto_beta(price_df, bench_ret):
        if price_df is None or price_df.empty or bench_ret.empty:
            return None
        stock_ret = indicators.compute_returns(price_df)["C-C Return"]
        return indicators.full_period_beta(stock_ret, bench_ret)
    bn_mode = st.radio(
        "Layout", ["Basket Calculator", "Pair-by-Pair"], horizontal=True, key="bn_mode",
        help="Basket Calculator: one or more stocks per side, sized as a basket. Pair-by-Pair: each row is "
        "its own long/short pair with its own gross 'slot' -- use this when you want fixed dollar slots per pair.",
    )

    # ----------------------------------------------------------------------
    # Basket Calculator
    # ----------------------------------------------------------------------
    if bn_mode == "Basket Calculator":
        st.markdown("##### Inputs")
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            bn_gross = st.number_input(
                "Gross exposure budget (long + short, R)", min_value=0.0, value=1_000_000.0, step=50_000.0, key="bn_gross",
            )
        with bc2:
            bn_capital = st.number_input(
                "Total capital, for cash left (R)", min_value=0.0, value=1_200_000.0, step=50_000.0, key="bn_capital",
            )
        with bc3:
            bn_weighting = st.radio(
                "Weighting within each side", ["Equal", "Custom"], horizontal=True, key="bn_weighting",
                help="Equal = every stock on a side gets the same share. Custom = use each row's own weight "
                "below (auto-normalised across that side).",
            )

        col_config = {
            "ticker": st.column_config.TextColumn("Stock / ticker"),
            "beta": st.column_config.NumberColumn("Beta", format="%.2f"),
            "custom_weight": st.column_config.NumberColumn(
                "Custom weight (optional)", format="%.2f",
                help="Only used in Custom mode; auto-normalised against the other rows on this side.",
            ),
        }
        bcc1, bcc2 = st.columns(2)
        with bcc1:
            st.markdown("**Long side**")
            bn_long_df = st.data_editor(
                pd.DataFrame({"ticker": ["", ""], "beta": [None, None], "custom_weight": [None, None]}),
                num_rows="dynamic", key="bn_long_editor", width="stretch", column_config=col_config,
            )
        with bcc2:
            st.markdown("**Short side**")
            bn_short_df = st.data_editor(
                pd.DataFrame({"ticker": ["", ""], "beta": [None, None], "custom_weight": [None, None]}),
                num_rows="dynamic", key="bn_short_editor", width="stretch", column_config=col_config,
            )
        st.caption("Add or remove rows as needed -- the template capped each side at 8, but this works for any number.")

        bn_res = ps.basket_calculator(bn_long_df, bn_short_df, bn_gross, weighting=bn_weighting, total_capital=bn_capital)

        st.divider()
        st.markdown("##### Results")
        r1, r2, r3 = st.columns(3)
        r1.metric("Long basket beta", f"{bn_res['beta_long']:.2f}")
        r2.metric("Short basket beta", f"{bn_res['beta_short']:.2f}")
        r3.metric("Net beta exposure", f"{bn_res['net_beta']:+.2f}", help="Should be ~zero.")

        r4, r5, r6 = st.columns(3)
        r4.metric("Long dollars (L)", f"R{bn_res['long_dollars']:,.0f}", help="L = G × β_short ÷ (β_long + β_short)")
        r5.metric("Short dollars (S)", f"R{bn_res['short_dollars']:,.0f}", help="S = G × β_long ÷ (β_long + β_short)")
        r6.metric("Long share of gross", f"{bn_res['long_share_of_gross']:.0%}")

        r7, r8, r9 = st.columns(3)
        r7.metric("Net dollar exposure (long − short)", f"R{bn_res['net_dollar_exposure']:,.0f}")
        r8.metric("Gross exposure (long + short)", f"R{bn_res['gross_exposure']:,.0f}")
        r9.metric("Cash left", f"R{bn_res['cash_left']:,.0f}" if bn_res["cash_left"] is not None else "—")

        st.markdown("###### Position per stock")
        pcol1, pcol2 = st.columns(2)

        def _fmt_positions(df):
            disp = df[["ticker", "beta", "weight", "position", "beta_weighted"]].copy()
            disp.columns = ["Stock / ticker", "Beta", "Effective weight", "Position (R)", "Beta-weighted (R)"]
            disp["Effective weight"] = disp["Effective weight"].map(lambda x: f"{x:.1%}")
            disp["Position (R)"] = disp["Position (R)"].map(lambda x: f"R{x:,.0f}")
            disp["Beta-weighted (R)"] = disp["Beta-weighted (R)"].map(lambda x: f"R{x:,.0f}")
            return disp

        with pcol1:
            st.caption("Long side")
            st.dataframe(_fmt_positions(bn_res["long_df"]), hide_index=True, width="stretch")
        with pcol2:
            st.caption("Short side")
            st.dataframe(_fmt_positions(bn_res["short_df"]), hide_index=True, width="stretch")

        st.markdown("###### Checks")
        for _label, _ok in bn_res["checks"].items():
            if _ok is None:
                st.caption(f"◽ {_label}: n/a")
            elif _ok:
                st.caption(f"✅ {_label}: OK")
            else:
                st.caption(f"⚠️ {_label}: CHECK")

    # ----------------------------------------------------------------------
    # Pair-by-Pair
    # ----------------------------------------------------------------------
    else:
        st.markdown("##### Inputs")
        pp1, pp2 = st.columns(2)
        with pp1:
            bn_default_slot = st.number_input(
                "Default gross slot per pair (R)", min_value=0.0, value=10_000.0, step=1_000.0, key="bn_default_slot",
                help="Used for any row where \"Slot override\" is blank.",
            )
        with pp2:
            bn_pp_capital = st.number_input("Total capital (R)", min_value=0.0, value=100_000.0, step=10_000.0, key="bn_pp_capital")

        # Auto-fill row 1 from whatever's picked in step ① -- only when that
        # selection actually changes, so rows the user has since added/edited
        # by hand aren't clobbered on every rerun.
        if trade_type == "Pairs trade (spread)":
            auto_long_ticker, auto_short_ticker = row_long["symbol"], row_short["symbol"]
            bench_ret = _bn_benchmark_returns(history_period)
            auto_long_beta = _bn_auto_beta(raw_long, bench_ret)
            auto_short_beta = _bn_auto_beta(raw_short, bench_ret)
        else:
            auto_long_ticker, auto_short_ticker = row["symbol"], ""
            bench_ret = _bn_benchmark_returns(history_period)
            auto_long_beta = _bn_auto_beta(raw, bench_ret)
            auto_short_beta = None

        # A data_editor's session-state key becomes "widget-owned" once it's
        # rendered, and Streamlit then refuses any direct assignment to that
        # key (by design -- it can't safely reconcile an external overwrite
        # against in-grid edits). So instead of overwriting the same key,
        # bump to a brand-new key whenever the auto-fill source changes --
        # a fresh key has no prior widget state, so passing its starting
        # value is just an ordinary (allowed) widget default. Reruns that
        # *don't* change step ① keep the same key, so Streamlit keeps
        # whatever the user has since edited in the grid instead of
        # resetting it.
        auto_src = (trade_type, auto_long_ticker, auto_short_ticker, history_period)
        if st.session_state.get("bn_pairs_auto_src") != auto_src:
            st.session_state["bn_pairs_auto_src"] = auto_src
            st.session_state["bn_pairs_version"] = st.session_state.get("bn_pairs_version", 0) + 1
        editor_key = f"bn_pairs_editor_{st.session_state.get('bn_pairs_version', 1)}"

        bn_pairs_default = pd.DataFrame(
            {
                "long_ticker": [auto_long_ticker], "long_beta": [auto_long_beta],
                "short_ticker": [auto_short_ticker], "short_beta": [auto_short_beta],
                "slot_override": [None],
            }
        )

        bn_pairs_df = st.data_editor(
            bn_pairs_default,
            num_rows="dynamic", key=editor_key, width="stretch",
            column_config={
                "long_ticker": st.column_config.TextColumn("Long stock"),
                "long_beta": st.column_config.NumberColumn("Long beta", format="%.2f"),
                "short_ticker": st.column_config.TextColumn("Short stock"),
                "short_beta": st.column_config.NumberColumn("Short beta", format="%.2f"),
                "slot_override": st.column_config.NumberColumn(
                    "Slot override (optional, R)", format="%.0f",
                    help="Leave blank to use the default gross slot per pair above.",
                ),
            },
        )
        st.caption(
            "Row 1 is auto-filled from step ① (ticker + beta vs. the JSE All Share over the same history "
            "period) and refreshes whenever you change the stock/pair up there -- edit any cell, or add more "
            "rows, to go beyond that. For an index hedge, put the index (e.g. the JSE Top 40) as the short "
            "leg; its beta auto-fills like any other instrument since it has real price history too."
        )

        bn_pp_res = ps.pair_by_pair(bn_pairs_df, default_slot=bn_default_slot, total_capital=bn_pp_capital)

        st.divider()
        st.markdown("##### Summary")
        s1, s2, s3 = st.columns(3)
        s1.metric("Gross exposure (long + short)", f"R{bn_pp_res['gross_exposure']:,.0f}")
        s2.metric("Cash left", f"R{bn_pp_res['cash_left']:,.0f}" if bn_pp_res["cash_left"] is not None else "—")
        s3.metric("Net beta exposure", f"{bn_pp_res['net_beta']:+.2f}", help="Should be ~zero across all pairs.")

        st.markdown("###### Per-pair detail")
        disp_pp = bn_pp_res["rows"][
            ["long_ticker", "long_beta", "short_ticker", "short_beta", "slot_used", "long_position", "short_position", "beta_check"]
        ].copy()
        disp_pp.columns = [
            "Long", "Long β", "Short", "Short β", "Slot used (R)", "Long position (R)", "Short position (R)", "Beta check",
        ]
        for _col in ["Slot used (R)", "Long position (R)", "Short position (R)"]:
            disp_pp[_col] = disp_pp[_col].map(lambda x: f"R{x:,.0f}")
        st.dataframe(disp_pp, hide_index=True, width="stretch")

        st.markdown("###### Checks")
        for _label, _ok in bn_pp_res["checks"].items():
            if _ok:
                st.caption(f"✅ {_label}: OK")
            else:
                st.caption(f"⚠️ {_label}: CHECK")
