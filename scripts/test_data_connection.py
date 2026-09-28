"""
Quick sanity check that yfinance can reach Yahoo Finance and pull JSE data
from wherever you're running this (your own machine, not the dev sandbox
this app was built in -- that sandbox has no route to Yahoo Finance).

Usage:
    python3 scripts/test_data_connection.py
"""
import sys

try:
    import yfinance as yf
except ImportError:
    print("yfinance is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

SAMPLE = [
    "NPN.JO", "SBK.JO", "SHP.JO", "4SI.JO", "SXM.JO",  # mega, large, mid, small, micro cap
    "^J203.JO", "^J200.JO",  # JSE All Share / Top 40 -- used for rolling beta & correlation
]

# Best-effort candidate tickers for the Relative Performance page's sector/industry
# benchmarks (see src/relative_performance.py). These were found via web research,
# not live-verified -- this block tells you which ones actually work from your
# machine. Anything that fails here just means that sector/industry falls back to
# a constructed (equal-weighted constituent) index in the app instead -- nothing
# breaks either way, this is purely informational.
INDEX_CANDIDATES = [
    ("JSE Mid Cap", "^J201.JO"),
    ("JSE Mid Cap (alt)", "J201.L"),
    ("JSE Small Cap", "J202.L"),
    ("Financials (sector)", "^J580.JO"),
    ("Financials (sector, alt)", "^J5800.JO"),
    ("Real Estate / SA Listed Property (sector)", "^J253.JO"),
    ("Real Estate (Capped Property ETF)", "STXPRO.JO"),
    ("Real Estate (Capped Property idx)", "^J254.JO"),
    ("Real Estate (FTSE JSE Real Estate)", "^J8670.JO"),
    ("Real Estate (10X Property ETF)", "PTXTEN.JO"),
    ("Industrials (sector)", "J520.L"),
    ("Banks (industry, Satrix ETF)", "STXBNK.JO"),
    ("Banks (industry)", "^J835.JO"),
    ("Banks (industry, alt)", "J835.L"),
    ("Diversified Mining (industry)", "^J177.JO"),
    ("Diversified Mining (industry, alt)", "J177.L"),
    ("Gold Mining (industry)", "J150.L"),
    ("Specialty Chemicals (industry)", "JCHES.JO"),
    ("Paper & Forest Products (industry)", "JFORE.JO"),
    # -- Broader named indices, added from a user-supplied ticker list.
    ("JSE SWIX All Share", "^J433.JO"),
    ("JSE Capped SWIX Top 40", "^J403N.JO"),
    ("JSE SWIX Top 40 (Satrix ETF)", "STXSWX.JO"),
    ("JSE SWIX Top 40", "^J403.JO"),
    ("JSE Large Cap", "^J205.JO"),
    ("JSE Global Investor Price Index", "^J501.JO"),
    ("JSE Capped RAFI All Share (Satrix ETF)", "STXRAF.JO"),
    ("JSE Capped RAFI All Share", "^J263.JO"),
    ("JSE Resource 10 (Satrix ETF)", "STXRES.JO"),
    ("JSE Resource 10", "^J210.JO"),
    ("JSE Financial 15 (Satrix ETF)", "STXFIN.JO"),
    ("JSE Financial 15", "^J212.JO"),
    ("JSE Industrial 25 (Satrix ETF)", "STXIND.JO"),
    ("JSE Industrial 25", "^J211.JO"),
    ("JSE Capped Industrial 25", "^J311.JO"),
    ("Information Technology (sector)", "^J9537.JO"),
    ("Materials (sector)", "^J510.JO"),
    ("Energy / Oil & Gas (sector)", "^J5000.JO"),
    ("Energy / Oil & Gas Producers (sector)", "^J6011.JO"),
    ("Consumer Discretionary / Consumer Services (sector)", "^J5300.JO"),
    ("Health Care (sector)", "^J4500.JO"),
]

print("Testing yfinance connectivity against a sample of JSE tickers...\n")
ok, failed = [], []
for t in SAMPLE:
    try:
        hist = yf.Ticker(t).history(period="5d")
        if hist.empty:
            failed.append((t, "empty history"))
        else:
            last_close = hist["Close"].iloc[-1]
            print(f"  OK   {t:10s} last close = {last_close:,.2f}  ({len(hist)} rows)")
            ok.append(t)
    except Exception as e:
        failed.append((t, str(e)))

print()
if failed:
    print(f"{len(failed)} ticker(s) failed:")
    for t, err in failed:
        print(f"  FAIL {t:10s} {err}")
    print(
        "\nA few failures among micro/small caps is expected (patchy Yahoo Finance "
        "coverage). If ALL tickers failed, check your internet connection or whether "
        "your network blocks query1.finance.yahoo.com / query2.finance.yahoo.com."
    )
else:
    print("All sample tickers returned data. You're good to run: streamlit run app.py")

print("\nChecking best-effort sector/industry index candidates (Relative Performance page)...")
print("(A FAIL here just means that line uses a constructed index in the app instead -- informational only.)\n")
for label, t in INDEX_CANDIDATES:
    try:
        hist = yf.Ticker(t).history(period="5d")
        if hist.empty:
            print(f"  FAIL {t:10s} {label:45s} empty history -> will use constructed index")
        else:
            last_close = hist["Close"].iloc[-1]
            print(f"  OK   {t:10s} {label:45s} last close = {last_close:,.2f}")
    except Exception as e:
        print(f"  FAIL {t:10s} {label:45s} {e} -> will use constructed index")
