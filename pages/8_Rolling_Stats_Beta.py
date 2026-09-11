import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data, indicators
from src.common import bootstrap
from src.theme import ACCENT, ACCENT_2, MUTED

bootstrap("Rolling Stats & Beta", "🧮")

st.title("🧮 Rolling Volatility, Beta & Correlation")
st.caption(
    "Reproduces DoR_Template.xlsx's rolling-volatility and beta/correlation sheets -- benchmarked against "
    "the JSE All Share and JSE Top 40 indices rather than the template's original US benchmarks."
)

universe = data.load_universe()

c1, c2, c3, c4 = st.columns([1.3, 2, 1, 1])
with c1:
    timeframe = st.selectbox("Timeframe", ["Daily", "Weekly", "Monthly"], index=0)
with c2:
    sector_filter = st.selectbox("Sector filter", ["All sectors"] + sorted(universe["gics_sector"].unique()))
    stock_universe = universe if sector_filter == "All sectors" else universe[universe["gics_sector"] == sector_filter]
with c3:
    label_to_ticker = {f"{r['symbol']} — {r['name']}": r["yf_ticker"] for _, r in stock_universe.iterrows()}
    if not label_to_ticker:
        st.warning("No stocks in this sector.")
        st.stop()
    choice = st.selectbox("Stock", options=sorted(label_to_ticker.keys()))
    ticker = label_to_ticker[choice]
with c4:
    history_period = st.selectbox("History", ["3y", "5y", "10y", "max"], index=2)


@st.cache_data(ttl=3600, show_spinner=False)
def _get_hist(t, period):
    return data.get_history(t, period=period, interval="1d")


with st.spinner("Fetching price history for the stock and benchmarks..."):
    stock_raw = _get_hist(ticker, history_period)
    bench_raw = {name: _get_hist(t, history_period) for name, t in data.BENCHMARKS.items()}

if stock_raw.empty:
    st.error(f"No price data available for {ticker}.")
    st.stop()

missing_benchmarks = [name for name, df in bench_raw.items() if df.empty]
if missing_benchmarks:
    st.warning(
        f"Couldn't fetch benchmark data for: {', '.join(missing_benchmarks)}. "
        "Beta/correlation against those will be skipped. Run `python3 scripts/test_data_connection.py` "
        "to check whether `^J203.JO` / `^J200.JO` are reachable from your machine."
    )

resample_freq = {"Daily": None, "Weekly": "W", "Monthly": "M"}[timeframe]


def _prep(df):
    d = df if resample_freq is None else data.resample_ohlc(df, resample_freq)
    return indicators.compute_returns(d)["C-C Return"]


stock_returns = _prep(stock_raw)
bench_returns = {name: _prep(df) for name, df in bench_raw.items() if not df.empty}

# --------------------------------------------------------------------------
# Rolling volatility
# --------------------------------------------------------------------------
st.divider()
st.subheader("Rolling volatility")

vol_windows = indicators.ROLLING_VOL_WINDOWS[timeframe]
vol_df = indicators.rolling_volatility(stock_returns, vol_windows)

latest_vol = vol_df.dropna(how="all").iloc[-1] if not vol_df.dropna(how="all").empty else None
if latest_vol is not None:
    cols = st.columns(len(vol_windows))
    for c, w in zip(cols, vol_windows):
        val = latest_vol.get(f"{w}D Rolling Std Dev")
        c.metric(f"{w}{timeframe[0]} Rolling Std Dev", f"{val:.2%}" if val == val else "—")

fig_vol = go.Figure()
colors = [ACCENT, ACCENT_2, "#FFB020", "#B36AE2"]
for i, w in enumerate(vol_windows):
    col = f"{w}D Rolling Std Dev"
    fig_vol.add_trace(go.Scatter(x=vol_df.index, y=vol_df[col], name=col, line=dict(width=1.4, color=colors[i % len(colors)])))
fig_vol.update_layout(height=380, yaxis_tickformat=".2%", yaxis_title="Rolling std dev of returns", xaxis_title="")
st.plotly_chart(fig_vol, width="stretch")

# --------------------------------------------------------------------------
# Rolling beta / correlation vs each benchmark
# --------------------------------------------------------------------------
st.divider()
st.subheader("Rolling beta & correlation vs. JSE benchmarks")

beta_windows = indicators.ROLLING_BETA_WINDOWS[timeframe]

if not bench_returns:
    st.info("No benchmark data available -- can't compute beta/correlation right now.")
    st.stop()

summary_rows = []
all_results = {}
for bench_name, b_returns in bench_returns.items():
    results = indicators.rolling_beta_correl(stock_returns, b_returns, beta_windows)
    all_results[bench_name] = results
    row = {"Benchmark": bench_name}
    for label, _ in beta_windows:
        beta_series = results[label]["beta"].dropna()
        correl_series = results[label]["correl"].dropna()
        row[f"{label} Beta"] = beta_series.iloc[-1] if not beta_series.empty else None
        row[f"{label} Correl"] = correl_series.iloc[-1] if not correl_series.empty else None
    summary_rows.append(row)

summary_df = pd.DataFrame(summary_rows).set_index("Benchmark")
display_summary = summary_df.copy()
for col in display_summary.columns:
    display_summary[col] = display_summary[col].map(lambda x: f"{x:.2f}" if x == x and x is not None else "—")
st.dataframe(display_summary, width="stretch")

c1, c2 = st.columns(2)
with c1:
    bench_pick = st.selectbox("Benchmark to chart", list(bench_returns.keys()))
with c2:
    window_pick = st.selectbox("Window to chart", [w[0] for w in beta_windows], index=0)

results = all_results[bench_pick]
beta_series = results[window_pick]["beta"].dropna()
correl_series = results[window_pick]["correl"].dropna()

fig_beta = go.Figure()
fig_beta.add_trace(go.Scatter(x=beta_series.index, y=beta_series, name="Rolling Beta", line=dict(color=ACCENT, width=1.6)))
fig_beta.add_hline(y=1, line_dash="dot", line_color=MUTED, annotation_text="Beta = 1")
fig_beta.update_layout(height=360, yaxis_title=f"Rolling {window_pick} Beta vs {bench_pick}", xaxis_title="")
st.plotly_chart(fig_beta, width="stretch")

fig_correl = go.Figure()
fig_correl.add_trace(go.Scatter(x=correl_series.index, y=correl_series, name="Rolling Correlation", line=dict(color=ACCENT_2, width=1.6)))
fig_correl.update_layout(height=320, yaxis_title=f"Rolling {window_pick} Correlation vs {bench_pick}", xaxis_title="", yaxis_range=[-1, 1])
st.plotly_chart(fig_correl, width="stretch")

st.caption(
    "Beta and correlation windows only start producing values once enough history has accumulated "
    "(e.g. a 5-year window needs ~5 years of overlapping data for both the stock and the benchmark)."
)
