import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data, indicators
from src.common import bootstrap
from src.theme import ACCENT, ACCENT_2, DOWN, MUTED, UP

bootstrap("Seasonality", "🗓️")

st.title("🗓️ Seasonality")
st.caption(
    "How this stock or index has historically behaved at different points in the calendar -- "
    "by month, by day of week, and across the trading year -- based on as much daily history as "
    "Yahoo Finance has. Seasonality is a historical tendency, not a forecast: treat it as one "
    "input among many, not a signal on its own."
)

universe = data.load_universe()

# --------------------------------------------------------------------------
# Picker -- a stock from the universe, or a JSE index
# --------------------------------------------------------------------------
c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    kind = st.radio("Look at", ["Stock", "Index"], horizontal=True, key="szn_kind")
with c2:
    if kind == "Stock":
        sector_filter = st.selectbox(
            "Sector filter", ["All sectors"] + sorted(universe["gics_sector"].unique()), key="szn_sector"
        )
        stock_universe = universe if sector_filter == "All sectors" else universe[universe["gics_sector"] == sector_filter]
        label_to_ticker = {f"{r['symbol']} — {r['name']}": r["yf_ticker"] for _, r in stock_universe.iterrows()}
        if not label_to_ticker:
            st.warning("No stocks in this sector.")
            st.stop()
        choice = st.selectbox("Stock", options=sorted(label_to_ticker.keys()), key="szn_stock")
        ticker = label_to_ticker[choice]
        display_name = choice.split(" — ")[0]
    else:
        choice = st.selectbox("Index", options=list(data.BENCHMARKS.keys()), key="szn_index")
        ticker = data.BENCHMARKS[choice]
        display_name = choice
with c3:
    history_period = st.selectbox("History", ["5y", "10y", "max"], index=2, key="szn_period")

# --------------------------------------------------------------------------
# Data -- always daily bars, regardless of the history length picked, since
# the weekday / day-of-year breakdowns below need real trading-day
# granularity (not whatever interval another page might be showing).
# --------------------------------------------------------------------------
raw = data.get_history(ticker, period=history_period, interval="1d")
if raw.empty:
    st.error(f"No price data available for {display_name}.")
    st.stop()

n_years = raw.index.year.nunique()
if n_years < 3:
    st.warning(
        f"Only about {n_years} year(s) of history available for {display_name} -- seasonality "
        "patterns from this little data aren't statistically meaningful yet. Showing what's "
        "available below, but treat it with caution."
    )

st.caption(
    f"Using {len(raw):,} daily bars from {raw.index.min().date()} to {raw.index.max().date()} "
    f"({n_years} calendar years)."
)

st.divider()

# --------------------------------------------------------------------------
# Monthly seasonality
# --------------------------------------------------------------------------
st.subheader(f"Monthly seasonality — {display_name}")
monthly_pivot = indicators.monthly_returns_table(raw)
if monthly_pivot.empty:
    st.info("Not enough data to compute monthly seasonality.")
else:
    month_stats = indicators.monthly_seasonality_stats(monthly_pivot)

    mc1, mc2 = st.columns([2, 1])
    with mc1:
        colors = [UP if v >= 0 else DOWN for v in month_stats["Avg Return"].fillna(0)]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=month_stats["Month"],
            y=month_stats["Avg Return"],
            marker_color=colors,
            customdata=np.stack([month_stats["% Positive"], month_stats["Years"]], axis=-1),
            hovertemplate="%{x}: %{y:.2%}<br>Positive in %{customdata[0]:.0f}% of %{customdata[1]:.0f} years<extra></extra>",
        ))
        fig.update_layout(
            height=380,
            yaxis_title="Average return",
            yaxis_tickformat=".1%",
            xaxis_title="",
            showlegend=False,
            title="Average return by calendar month",
        )
        st.plotly_chart(fig, width="stretch")
    with mc2:
        has_data = month_stats["Avg Return"].notna().any()
        if has_data:
            best_row = month_stats.loc[month_stats["Avg Return"].idxmax()]
            worst_row = month_stats.loc[month_stats["Avg Return"].idxmin()]
            top_hit = month_stats.loc[month_stats["% Positive"].idxmax()]
            st.metric(f"Best month on average — {best_row['Month']}", f"{best_row['Avg Return']:+.2%}")
            st.metric(f"Worst month on average — {worst_row['Month']}", f"{worst_row['Avg Return']:+.2%}")
            st.metric(
                f"Highest hit rate — {top_hit['Month']}",
                f"{top_hit['% Positive']:.0f}% of {int(top_hit['Years'])} yrs",
            )
        else:
            st.info("Not enough data for month-by-month highlights.")

    display_stats = month_stats.copy()
    for col in ["Avg Return", "Median Return", "Std Dev"]:
        display_stats[col] = display_stats[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "—")
    display_stats["% Positive"] = display_stats["% Positive"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
    st.dataframe(display_stats, hide_index=True, width="stretch")

st.divider()

# --------------------------------------------------------------------------
# Year x Month heatmap
# --------------------------------------------------------------------------
st.subheader("Monthly returns by year")
if monthly_pivot.empty:
    st.info("Not enough data to build a monthly returns grid.")
else:
    heat_avg = indicators.append_grid_averages(monthly_pivot[indicators.MONTH_NAMES])
    year_rows = heat_avg.drop(index="Avg").sort_index(ascending=False)
    heat = pd.concat([year_rows, heat_avg.loc[["Avg"]]])
    z = heat.values * 100
    fig_heat = go.Figure(data=go.Heatmap(
        z=z,
        x=indicators.MONTH_NAMES + ["Avg"],
        y=[str(y) for y in heat.index],
        colorscale=[[0, DOWN], [0.5, "#1A1F2B"], [1, UP]],
        zmid=0,
        text=[[f"{v:.1f}%" if pd.notna(v) else "" for v in row] for row in z],
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
        colorbar=dict(title="Return", tickformat=".0f", ticksuffix="%"),
    ))
    fig_heat.update_layout(height=max(320, 28 * len(heat) + 80), xaxis_title="", yaxis_title="")
    st.plotly_chart(fig_heat, width="stretch")
    st.caption(
        "Each cell is that calendar month's % return (month-end to month-end). Blank cells mean no "
        "data for that month (e.g. the stock's listing year, or the current partial year). The 'Avg' "
        "column is each year's average monthly return; the 'Avg' row is each calendar month's average "
        "return across all years."
    )

st.divider()

# --------------------------------------------------------------------------
# Weekly returns by year
# --------------------------------------------------------------------------
st.subheader("Weekly returns by year")
weekly_pivot = indicators.weekly_returns_table(raw)
if weekly_pivot.empty:
    st.info("Not enough data to build a weekly returns grid.")
else:
    weekly_heat_avg = indicators.append_grid_averages(weekly_pivot)
    weekly_year_rows = weekly_heat_avg.drop(index="Avg").sort_index(ascending=False)
    weekly_heat = pd.concat([weekly_year_rows, weekly_heat_avg.loc[["Avg"]]])
    wz = weekly_heat.values * 100
    fig_weekly_heat = go.Figure(data=go.Heatmap(
        z=wz,
        x=indicators.WEEK_COLUMNS + ["Avg"],
        y=[str(y) for y in weekly_heat.index],
        colorscale=[[0, DOWN], [0.5, "#1A1F2B"], [1, UP]],
        zmid=0,
        hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
        colorbar=dict(title="Return", tickformat=".0f", ticksuffix="%"),
    ))
    shown_week_ticks = [indicators.WEEK_COLUMNS[i] for i in range(0, 53, 4)]
    fig_weekly_heat.update_layout(
        height=max(320, 22 * len(weekly_heat) + 80), xaxis_title="", yaxis_title="",
        xaxis=dict(tickmode="array", tickvals=shown_week_ticks + ["Avg"], ticktext=shown_week_ticks + ["Avg"]),
    )
    st.plotly_chart(fig_weekly_heat, width="stretch")
    st.caption(
        "Each cell is that ISO week's % return (Friday close to Friday close) -- W1 is the first ISO "
        "week of the year. With 53 columns there isn't room to label every cell, so hover over one to "
        "see its exact value. Same 'Avg' row/column as the monthly grid above: average per year on the "
        "right, average per calendar week across all years on the bottom."
    )

st.divider()

# --------------------------------------------------------------------------
# Day-of-week seasonality
# --------------------------------------------------------------------------
st.subheader("Day-of-week seasonality")
wd_stats = indicators.weekday_seasonality_stats(raw)
if wd_stats.empty or wd_stats["Count"].sum() == 0:
    st.info("Not enough daily data to compute a day-of-week breakdown.")
else:
    wc1, wc2 = st.columns([2, 1])
    with wc1:
        colors_wd = [UP if v >= 0 else DOWN for v in wd_stats["Avg Return"].fillna(0)]
        fig_wd = go.Figure()
        fig_wd.add_trace(go.Bar(
            x=wd_stats["Day"],
            y=wd_stats["Avg Return"],
            marker_color=colors_wd,
            customdata=np.stack([wd_stats["% Positive"], wd_stats["Count"]], axis=-1),
            hovertemplate="%{x}: %{y:.3%}<br>Positive in %{customdata[0]:.0f}% of %{customdata[1]:.0f} days<extra></extra>",
        ))
        fig_wd.update_layout(
            height=340, yaxis_title="Average return", yaxis_tickformat=".2%", xaxis_title="", showlegend=False
        )
        st.plotly_chart(fig_wd, width="stretch")
    with wc2:
        display_wd = wd_stats.copy()
        display_wd["Avg Return"] = display_wd["Avg Return"].map(lambda x: f"{x:.3%}" if pd.notna(x) else "—")
        display_wd["% Positive"] = display_wd["% Positive"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
        st.dataframe(display_wd, hide_index=True, width="stretch")
    st.caption("Based on Close-to-Close daily returns. JSE-listed names trade Mon-Fri, so weekends aren't shown.")

st.divider()

# --------------------------------------------------------------------------
# Seasonal average path across the trading year
# --------------------------------------------------------------------------
st.subheader("Seasonal path through the year")
paths, avg_path = indicators.seasonal_average_path(raw)
if avg_path.empty:
    st.info("Not enough complete calendar years to build a seasonal path chart.")
else:
    fig_path = go.Figure()
    for year, path in paths.items():
        fig_path.add_trace(go.Scatter(
            x=list(path.index),
            y=path.values,
            mode="lines",
            line=dict(width=1, color=MUTED),
            opacity=0.28,
            name=str(year),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig_path.add_trace(go.Scatter(
        x=list(avg_path.index),
        y=avg_path.values,
        mode="lines",
        line=dict(width=3, color=ACCENT),
        name=f"Average ({len(paths)} yrs)",
        hovertemplate="Trading day %{x}: %{y:+.2f}%<extra>Average</extra>",
    ))
    today_tday = indicators.current_trading_day_of_year()
    if today_tday <= avg_path.index.max():
        fig_path.add_vline(
            x=today_tday, line_dash="dot", line_color=ACCENT_2, opacity=0.8,
            annotation_text="Today", annotation_position="top",
        )
    fig_path.update_layout(
        height=460,
        xaxis_title="",
        yaxis_title="Cumulative return from start of year",
        yaxis_tickformat=".1f",
        yaxis_ticksuffix="%",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig_path.update_xaxes(tickmode="array", tickvals=indicators._APPROX_MONTH_START_TDAY, ticktext=indicators.MONTH_NAMES)
    st.plotly_chart(fig_path, width="stretch")
    st.caption(
        f"Grey lines are each individual calendar year's path (rebased to 0% at that year's first "
        f"trading day); the highlighted line is the average across all {len(paths)} complete years. "
        "Month labels on the x-axis are approximate (based on ~21 trading days/month), since the "
        "exact trading-day count per month varies slightly year to year. This shows the historical "
        "*shape* of the year, not a prediction of this year's path."
    )
