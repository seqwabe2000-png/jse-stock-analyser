"""
Lets analysis pages (Charts, Distribution of Returns, ATR %, Rolling Stats
& Beta, Pairs Trade, Stops & Targets) offer a JSE index as a pickable
"instrument" alongside individual stocks -- so the same chart / stat /
stop-sizing tools that already work on a stock also work on the Top 40,
All Share, a sector index, and so on.

Only indices with at least one candidate real Yahoo Finance ticker (see
BROAD_INDEX_CANDIDATES / SECTOR_INDEX_CANDIDATES / INDUSTRY_INDEX_CANDIDATES
in src/relative_performance.py) are included here: these pages need actual
OHLC (High/Low, not just Close) for candles / True Range % / 52-week
ranges / etc., which only a real daily price series can give. A
constructed cap-weighted proxy (relative_performance.py's fallback for the
handful of sectors with no known index ticker at all, e.g. Communication
Services) is a *return* series only, with no real daily High/Low, so it
isn't offered as a pickable instrument here -- it's still viewable,
honestly labelled as constructed, on pages/14_Indices.py, and (for
return-only stats) pages/9_Relative_Performance.py and
pages/13_Seasonality.py already support it a different way.

Each index gets a short, ticker-like code as its "symbol" (e.g. "TOP40",
"BANKX") purely so it drops straight into every page's existing
"{symbol} — {name}" label/caption pattern without having to special-case
every place a stock's symbol gets displayed.
"""
import numpy as np
import pandas as pd

from src import data
from src import relative_performance as rp

BROAD_INDEX_CODES = {
    "JSE All Share": "ALSI",
    "JSE Top 40": "TOP40",
    "JSE Mid Cap": "MIDCAP",
    "JSE Small Cap": "SMLCAP",
    "JSE SWIX All Share": "SWIXALL",
    "JSE Capped SWIX Top 40": "CSWIXT40",
    "JSE SWIX Top 40": "SWIXT40",
    "JSE Large Cap": "LRGCAP",
    "JSE Global Investor Price Index": "GIPI",
    "JSE Capped RAFI All Share": "RAFI",
    "JSE Resource 10": "RESI10",
    "JSE Financial 15": "FINI15",
    "JSE Industrial 25": "INDI25",
    "JSE Capped Industrial 25": "CINDI25",
}
SECTOR_INDEX_CODES = {
    "Financials": "FINX",
    "Real Estate": "REIX",
    "Industrials": "INDX",
    "Information Technology": "TECX",
    "Materials": "MATX",
    "Energy": "ENGX",
    "Consumer Discretionary": "DISX",
    "Health Care": "HLTX",
}
INDUSTRY_INDEX_CODES = {
    "Banks": "BANKX",
    "Diversified Mining": "MINX",
    "Gold Mining": "GLDX",
    "Specialty Chemicals": "CHEX",
    "Paper & Forest Products": "PAPX",
}

INSTRUMENT_COLUMNS = [
    "symbol", "name", "yf_ticker", "candidates", "market_cap_tier", "gics_sector", "industry", "market_cap_zar",
]


def _row(symbol, name, candidates, tier, category):
    return {
        "symbol": symbol,
        "name": name,
        "yf_ticker": candidates[0],
        "candidates": list(candidates),
        "market_cap_tier": tier,
        "gics_sector": "Index",
        "industry": category,
        "market_cap_zar": np.nan,
    }


def index_rows() -> pd.DataFrame:
    """One row per index with a known candidate Yahoo Finance ticker,
    shaped like a slice of data.load_universe()'s output (plus a
    'candidates' column listing every candidate ticker, tried in order at
    fetch time) so it concatenates straight onto it. All index rows share
    gics_sector="Index", so an existing "Sector filter" dropdown elsewhere
    in a page automatically gets a new "Index" option that shows just
    these, with no extra UI code needed."""
    rows = []
    for name, candidates in rp.BROAD_INDEX_CANDIDATES.items():
        rows.append(_row(BROAD_INDEX_CODES.get(name, "IDX"), name, candidates, "Broad Market Index", "Broad market"))
    for sector, candidates in rp.SECTOR_INDEX_CANDIDATES.items():
        rows.append(_row(SECTOR_INDEX_CODES.get(sector, "SECX"), f"{sector} (sector index)", candidates, "Sector Index", "Sector"))
    for industry, candidates in rp.INDUSTRY_INDEX_CANDIDATES.items():
        rows.append(_row(INDUSTRY_INDEX_CODES.get(industry, "INDX"), f"{industry} (industry index)", candidates, "Industry Index", "Industry"))
    return pd.DataFrame(rows, columns=INSTRUMENT_COLUMNS)


def with_indices(universe: pd.DataFrame) -> pd.DataFrame:
    """`universe` (data.load_universe()'s output) with index rows appended
    -- use this as the source for any "Stock" picker that should also
    offer indices.

    Don't use this for Screener-style aggregate logic that sums
    market_cap_zar across a sector/tier -- an index row's market cap is
    NaN on purpose (it would otherwise double-count alongside its own
    constituent stocks)."""
    stocks = universe.copy()
    stocks["candidates"] = None
    return pd.concat([stocks, index_rows()], ignore_index=True, sort=False)


def get_history_for_row(row, period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    """A stock row (no 'candidates') fetches the plain way; an index row
    resolves across its candidate tickers, trying each in order until one
    actually returns data -- the same best-effort resolution
    src/relative_performance.py already uses elsewhere in the app."""
    candidates = row.get("candidates") if hasattr(row, "get") else None
    if isinstance(candidates, list) and candidates:
        df, _used = rp.resolve_index_ohlc(candidates, period=period, interval=interval)
        return df if df is not None else pd.DataFrame()
    return data.get_history(row["yf_ticker"], period=period, interval=interval)


def is_index_row(row) -> bool:
    candidates = row.get("candidates") if hasattr(row, "get") else None
    return isinstance(candidates, list) and len(candidates) > 0
