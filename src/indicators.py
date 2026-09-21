"""
Technical indicator + statistics helpers shared across pages.
"""
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def add_all_smas(df: pd.DataFrame, price_col: str = "Close", windows=(20, 50, 100, 200)) -> pd.DataFrame:
    out = df.copy()
    for w in windows:
        out[f"SMA{w}"] = sma(out[price_col], w)
    return out


def pct_above_sma(df: pd.DataFrame, window: int = 200, price_col: str = "Close"):
    """Returns True/False/None for whether the latest close is above its
    SMA(window); None if not enough history."""
    s = sma(df[price_col], window)
    if s.empty or pd.isna(s.iloc[-1]) or pd.isna(df[price_col].iloc[-1]):
        return None
    return bool(df[price_col].iloc[-1] > s.iloc[-1])


def breadth_time_series(hist: dict, window: int = 200, price_col: str = "Close", min_sample: int = 5) -> pd.Series:
    """For each trading day, the % of the given tickers' cached histories
    that were trading above their own SMA(window) on that day -- the
    "breadth over time" line (e.g. the classic "% of stocks above their
    200-day moving average" chart), built entirely from data already
    fetched for a single snapshot breadth scan (no extra network calls).

    `hist` is a {ticker: OHLCV DataFrame} dict as returned by
    data.get_history_bulk. A ticker only contributes to a given day once it
    has `window` bars of history; days where fewer than `min_sample`
    tickers have a value are dropped (avoids a noisy, meaningless % at the
    very start of the window when almost nothing has a valid SMA yet).
    Returns a Series (0-100) indexed by date, empty if nothing qualifies.
    """
    above_cols = {}
    for ticker, df in hist.items():
        if df is None or df.empty or price_col not in df.columns or len(df) <= window:
            continue
        close = df[price_col]
        s = sma(close, window)
        above = (close > s).astype(float)
        above[s.isna() | close.isna()] = np.nan
        above_cols[ticker] = above

    if not above_cols:
        return pd.Series(dtype=float)

    combined = pd.concat(above_cols, axis=1).sort_index()
    sample_count = combined.notna().sum(axis=1)
    pct_above = combined.mean(axis=1, skipna=True) * 100
    return pct_above[sample_count >= min_sample]


# --------------------------------------------------------------------------
# True Range % (ATRP template semantics: MAX(H-L, |H-PrevClose|, |PrevClose-L|) / Open)
# --------------------------------------------------------------------------
def true_range_pct(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (prev_close - df["Low"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr / df["Open"]


# Horizon tables reproduced exactly from ATRP_Template.xlsx (one sheet/list
# per frequency -- "1 Week" means 5 *trading days*, not 5 weekly bars, etc.)
ATRP_HORIZONS = {
    "Daily": [
        ("1 Week", 5), ("1 Month", 20), ("1 Quarter", 60), ("1 Year", 250),
        ("3 Years", 750), ("5 Years", 1250), ("10 Years", 2500),
        ("20 Years", 5000), ("50 Years", 12500),
    ],
    "Weekly": [
        ("1 Month", 4), ("1 Quarter", 12), ("1 Year", 52), ("3 Years", 156),
        ("5 Years", 260), ("10 Years", 520), ("20 Years", 1040), ("50 Years", 2600),
    ],
    "Monthly": [
        ("1 Quarter", 3), ("1 Year", 12), ("3 Years", 36), ("5 Years", 60),
        ("10 Years", 120), ("20 Years", 240), ("50 Years", 600),
    ],
    "Quarterly": [
        ("1 Year", 4), ("3 Years", 12), ("5 Years", 20), ("10 Years", 40),
        ("20 Years", 80), ("50 Years", 200),
    ],
}


def average_true_range_pct(df: pd.DataFrame, horizons) -> pd.DataFrame:
    trp = true_range_pct(df).dropna()
    rows = []
    for label, n in horizons:
        window = trp.tail(n)
        rows.append({"Horizon": label, "Trading Periods": n, "Avg True Range %": window.mean() if len(window) else np.nan,
                      "Periods Available": len(window)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Returns + distribution stats (DoR template semantics)
# --------------------------------------------------------------------------
def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["C-C Return"] = df["Adj Close"].pct_change()
    out["H-L Return"] = (df["High"] - df["Low"]) / df["Low"]
    out["O-C Return"] = (df["Close"] - df["Open"]) / df["Open"]
    # Overnight gap: today's Open vs. the *previous* bar's Close -- captures
    # jumps that happen between sessions (news, results releases, overseas
    # market moves) rather than intraday moves.
    out["C-O Return"] = (df["Open"] - df["Close"].shift(1)) / df["Close"].shift(1)
    return out.dropna(how="all")


PERIODS_PER_YEAR = {"Daily": 252, "Weekly": 52, "Monthly": 12, "Quarterly": 4}


def descriptive_stats(series: pd.Series, periods_per_year: int) -> dict:
    s = series.dropna()
    if s.empty:
        return {}
    mean = s.mean()
    std = s.std(ddof=1)
    return {
        "Mean": mean,
        "Standard Error": std / np.sqrt(len(s)) if len(s) else np.nan,
        "Median": s.median(),
        "Mode": s.mode().iloc[0] if not s.mode().empty else np.nan,
        "Standard Deviation": std,
        "Sample Variance": s.var(ddof=1),
        "Kurtosis": s.kurt(),
        "Skewness": s.skew(),
        "Range": s.max() - s.min(),
        "Minimum": s.min(),
        "Maximum": s.max(),
        "Sum": s.sum(),
        "Count": len(s),
        "Annualised Mean": mean * periods_per_year,
        "Annualised Std Dev": std * np.sqrt(periods_per_year),
    }


# --------------------------------------------------------------------------
# Rolling volatility + rolling beta/correlation vs a benchmark
# (DoR_Template.xlsx's "Rolling Vol" / "RollingStats-Beta&Correl" sheets,
# adapted to use JSE All Share / Top 40 as the benchmarks instead of the
# template's original S&P500/NASDAQ100)
# --------------------------------------------------------------------------
ROLLING_VOL_WINDOWS = {"Daily": [30, 60, 90, 120], "Weekly": [4, 13, 26, 52], "Monthly": [3, 6, 12, 24]}
ROLLING_BETA_WINDOWS = {
    "Daily": [("1 Year", 252), ("2 Years", 504), ("5 Years", 1260)],
    "Weekly": [("1 Year", 52), ("2 Years", 104), ("5 Years", 260)],
    "Monthly": [("1 Year", 12), ("2 Years", 24), ("5 Years", 60)],
}


def rolling_volatility(returns: pd.Series, windows) -> pd.DataFrame:
    out = pd.DataFrame(index=returns.index)
    for w in windows:
        out[f"{w}D Rolling Std Dev"] = returns.rolling(window=w, min_periods=w).std()
    return out


def rolling_beta_correl(stock_returns: pd.Series, bench_returns: pd.Series, windows) -> dict:
    """windows: list of (label, n) trading-period tuples. Returns
    {label: {"beta": Series, "correl": Series}} aligned on the shared index."""
    aligned = pd.concat({"stock": stock_returns, "bench": bench_returns}, axis=1).dropna()
    results = {}
    for label, n in windows:
        cov = aligned["stock"].rolling(window=n, min_periods=n).cov(aligned["bench"])
        var = aligned["bench"].rolling(window=n, min_periods=n).var()
        beta = cov / var.replace(0, pd.NA)
        correl = aligned["stock"].rolling(window=n, min_periods=n).corr(aligned["bench"])
        results[label] = {"beta": beta, "correl": correl}
    return results


def event_window(df: pd.DataFrame, event_date, window: int = 10, price_col: str = "Close"):
    """Cumulative % return path around a single event date, indexed to the
    close on the trading day immediately before the event (relative day 0
    is the event day itself). Returns a pandas Series indexed by relative
    trading-day offset (-window..+window), or None if the event date isn't
    covered by the price history."""
    dates = df.index.normalize()
    event_ts = pd.Timestamp(event_date).normalize()
    matches = dates[dates == event_ts]
    if len(matches) == 0:
        # fall back to the next available trading day (e.g. weekend announcement)
        later = dates[dates >= event_ts]
        if len(later) == 0:
            return None
        event_ts = later[0]

    pos = dates.get_indexer([event_ts])[0]
    if pos <= 0:
        return None  # need at least one prior day as the base

    lo = max(0, pos - window)
    hi = min(len(df), pos + window + 1)
    base = df[price_col].iloc[pos - 1]
    if base == 0 or pd.isna(base):
        return None

    window_prices = df[price_col].iloc[lo:hi]
    cum_return = (window_prices / base - 1) * 100
    cum_return.index = range(lo - pos, hi - pos)
    return cum_return


PERIOD_RETURN_LABELS = ["1D", "WTD", "MTD", "QTD", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX"]


def _closest_close_on_or_before(series: pd.Series, target):
    eligible = series[series.index <= pd.Timestamp(target)]
    return eligible.iloc[-1] if len(eligible) else None


def period_returns(close: pd.Series) -> dict:
    """% change from the last available close back to the start of each
    standard lookback window (1D/WTD/MTD/QTD/YTD/1Y/3Y/5Y/10Y/MAX). `close`
    should be as long a daily history as you can fetch (ideally period=
    "max") -- a short window means the longer lookbacks just won't be
    available and are omitted rather than wrong."""
    s = close.dropna()
    if s.empty:
        return {}
    end_date = s.index.max()
    last = s.iloc[-1]
    out = {}

    if len(s) >= 2:
        out["1D"] = (last / s.iloc[-2] - 1) * 100

    week_start = end_date - relativedelta(days=end_date.weekday())
    base = _closest_close_on_or_before(s, week_start - relativedelta(days=1))
    if base:
        out["WTD"] = (last / base - 1) * 100

    month_start = pd.Timestamp(end_date.year, end_date.month, 1)
    base = _closest_close_on_or_before(s, month_start - relativedelta(days=1))
    if base:
        out["MTD"] = (last / base - 1) * 100

    q_start_month = 3 * ((end_date.month - 1) // 3) + 1
    quarter_start = pd.Timestamp(end_date.year, q_start_month, 1)
    base = _closest_close_on_or_before(s, quarter_start - relativedelta(days=1))
    if base:
        out["QTD"] = (last / base - 1) * 100

    base = _closest_close_on_or_before(s, pd.Timestamp(end_date.year - 1, 12, 31))
    if base:
        out["YTD"] = (last / base - 1) * 100

    for label, years in [("1Y", 1), ("3Y", 3), ("5Y", 5), ("10Y", 10)]:
        base = _closest_close_on_or_before(s, end_date - relativedelta(years=years))
        if base and (end_date - relativedelta(years=years)) >= s.index.min():
            out[label] = (last / base - 1) * 100

    out["MAX"] = (last / s.iloc[0] - 1) * 100
    return out


def distribution_bins(series: pd.Series, n_std_range: float = 3.0, step: float = 0.6) -> pd.DataFrame:
    """Reproduces the DoR template's histogram: bin edges at mean + k*std for
    k = -3.0 .. +3.0 in `step` increments, with an open-ended first ("Less
    than") and last ("More than") bucket."""
    s = series.dropna()
    if s.empty:
        return pd.DataFrame(columns=["Range", "Frequency", "Probability", "Cumulative Probability"])

    mean, std = s.mean(), s.std(ddof=1)
    ks = np.arange(-n_std_range, n_std_range + 1e-9, step)
    edges = [mean + k * std for k in ks]

    labels, freqs = [], []
    labels.append(f"Less than {edges[0]:.2%}")
    freqs.append((s <= edges[0]).sum())
    for lo, hi in zip(edges[:-1], edges[1:]):
        labels.append(f"{lo:.2%} to {hi:.2%}")
        freqs.append(((s > lo) & (s <= hi)).sum())
    labels.append(f"Greater than {edges[-1]:.2%}")
    freqs.append((s > edges[-1]).sum())

    total = len(s)
    prob = [f / total for f in freqs]
    cum = np.cumsum(prob)
    return pd.DataFrame(
        {"Range": labels, "Frequency": freqs, "Probability": prob, "Cumulative Probability": cum}
    )


# --------------------------------------------------------------------------
# Percentile table + empirical distribution (DoR template's percentile and
# "empirical distribution" sheets)
# --------------------------------------------------------------------------
PERCENTILES = list(range(1, 100))


def percentile_table(series: pd.Series) -> pd.DataFrame:
    """1st-99th percentile of the return series, one row per percentile."""
    s = series.dropna()
    if s.empty:
        return pd.DataFrame(columns=["Percentile", "Value"])
    values = np.percentile(s, PERCENTILES)
    return pd.DataFrame({"Percentile": PERCENTILES, "Value": values})


def empirical_distribution(series: pd.Series) -> dict:
    """Positive/Negative/Zero breakdown (avg return, count, frequency %,
    frequency-adjusted return = avg return * frequency) plus the mean +/-
    1/2/3 std-dev band table (upper/lower bound, actual count/%, and the
    theoretical normal-distribution % for comparison)."""
    s = series.dropna()
    if s.empty:
        return {"buckets": pd.DataFrame(), "bands": pd.DataFrame()}

    total = len(s)
    pos, neg, zero = s[s > 0], s[s < 0], s[s == 0]

    def _row(label, sub):
        avg = sub.mean() if len(sub) else 0.0
        freq = len(sub) / total if total else 0.0
        return {
            "Category": label,
            "Average Returns": avg,
            "Count": len(sub),
            "Frequency %": freq * 100,
            "Frequency Adjusted Return": avg * freq,
        }

    buckets = pd.DataFrame([_row("Positive Data Points", pos), _row("Negative Data Points", neg), _row("Zero", zero)])

    mean, std = s.mean(), s.std(ddof=1)
    normal_pct = {1: 68.27, 2: 95.45, 3: 99.73}
    band_rows = []
    for k in (1, 2, 3):
        upper, lower = mean + k * std, mean - k * std
        actual = ((s >= lower) & (s <= upper)).sum()
        band_rows.append(
            {
                "Std Dev": k,
                "Upper Bound": upper,
                "Lower Bound": lower,
                "Actual Count": actual,
                "Actual % Count": actual / total * 100 if total else 0.0,
                "Normal % Count": normal_pct[k],
            }
        )
    bands = pd.DataFrame(band_rows)
    return {"buckets": buckets, "bands": bands}


# --------------------------------------------------------------------------
# Swing highs/lows, support/resistance zones, and swing trend lines (Charts
# page). Deliberately limited to the underlying levels/lines rather than
# naming shapes like "head and shoulders" -- see README for why.
# --------------------------------------------------------------------------
def find_swing_points(df: pd.DataFrame, order: int = 5):
    """A bar is a swing high if its High is the max within `order` bars on
    both sides (swing low: analogous on Low). Returns (swing_highs,
    swing_lows) as Series of price values indexed by date."""
    from scipy.signal import argrelextrema

    if len(df) < order * 2 + 1:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    high_idx = argrelextrema(df["High"].values, np.greater_equal, order=order)[0]
    low_idx = argrelextrema(df["Low"].values, np.less_equal, order=order)[0]
    swing_highs = df["High"].iloc[high_idx]
    swing_lows = df["Low"].iloc[low_idx]
    return swing_highs, swing_lows


def support_resistance_zones(swing_highs: pd.Series, swing_lows: pd.Series, tolerance: float = 0.02,
                               min_touches: int = 2, top_n: int = 4):
    """Cluster swing-high prices (resistance candidates) and swing-low
    prices (support candidates) into zones -- prices within `tolerance`
    (fractional, e.g. 0.02 = 2%) of each other are grouped together. Only
    zones touched at least `min_touches` times are kept, ranked by touch
    count, capped at `top_n` each. Returns (resistance_zones,
    support_zones), each a list of {"level", "touches", "low", "high"}."""

    def _cluster(prices: pd.Series):
        if prices.empty:
            return []
        vals = sorted(float(v) for v in prices.values)
        clusters, current = [], [vals[0]]
        for v in vals[1:]:
            if v <= current[-1] * (1 + tolerance):
                current.append(v)
            else:
                clusters.append(current)
                current = [v]
        clusters.append(current)
        zones = [
            {"level": float(np.mean(c)), "touches": len(c), "low": min(c), "high": max(c)}
            for c in clusters
            if len(c) >= min_touches
        ]
        zones.sort(key=lambda z: z["touches"], reverse=True)
        return zones[:top_n]

    return _cluster(swing_highs), _cluster(swing_lows)


def fit_trend_line(swing_points: pd.Series, n_points: int = 3):
    """Least-squares line through the most recent `n_points` swing points
    (a swing-low series for an uptrend/support line, a swing-high series
    for a downtrend/resistance line). Returns None if there aren't at least
    2 points, otherwise {"x": [date0, date1], "y": [price0, price1]} for
    the segment spanning from the first point used to today (so it's drawn
    all the way to the current bar, extended if needed)."""
    pts = swing_points.tail(n_points)
    if len(pts) < 2:
        return None
    x_ord = np.array([d.toordinal() for d in pts.index], dtype=float)
    y = pts.values.astype(float)
    slope, intercept = np.polyfit(x_ord, y, 1)
    x0 = x_ord.min()
    return {"slope": slope, "intercept": intercept, "x0_ordinal": x0, "start_date": pts.index.min()}
