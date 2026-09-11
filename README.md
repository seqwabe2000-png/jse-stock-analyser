# JSE Stock Analyser — complete (Phases 1–3)

A Koyfin-style screener and charting tool for the Johannesburg Stock Exchange, built in Python with Streamlit. All three planned phases are done: login, the full JSE stock universe, market-cap/sector/industry grouping, price charts with indicators, market breadth, distribution-of-returns, ATR%, SENS/news, and announcement event-study are all working.

## What's built

1. **Login** — simple password-gated access (`src/auth.py`). Default credentials `admin` / `jse2026` — **change this before relying on it** (see Setup below).
2. **JSE universe** (`data/jse_universe.csv`) — 259 JSE-listed instruments with ticker, name, market-cap tier, GICS sector, and industry/subsector.
3. **Screener** (`pages/1_📊_Screener.py`) — filter and group the whole universe by market-cap tier, GICS sector, or industry, with optional live price/% change/200-SMA signal.
4. **Charts** (`pages/2_📈_Charts.py`) — candlestick chart per stock with 20/50/100/200-day SMAs, Bollinger Bands, RSI, and MACD, TradingView-style.
5. **Market Breadth** (`pages/3_🌡️_Market_Breadth.py`) — % of stocks above a chosen SMA, market-wide and broken down by sector and industry.
6. **Distribution of Returns** (`pages/4_📉_Distribution_of_Returns.py`) — reproduces `DoR_Template.xlsx`: C-C / H-L / O-C return distributions at daily/weekly/monthly/quarterly frequency, filterable by sector and stock, with the same descriptive-statistics block (mean, std error, median, mode, std dev, variance, kurtosis, skewness, annualised mean/std, etc.) and mean±k·σ histogram bins as the template.
7. **ATR %** (`pages/5_📐_ATR_Percent.py`) — reproduces `ATRP_Template.xlsx`: True Range % = MAX(High−Low, |High−PrevClose|, |PrevClose−Low|) ÷ Open, averaged over the exact same horizon windows the template uses per frequency (1 week through 50 years for Daily; scaled equivalents for Weekly/Monthly/Quarterly), filterable by timeframe, sector, and stock.
8. **SENS & News** (`pages/6_📰_SENS_News.py`) — SENS announcements for a selected stock (scraped from Sharenet's public SENS page, since there's no free official JSE SENS API), plus recent company news and sector news via Google News.
9. **Event Study** (`pages/7_🗓️_Event_Study.py`) — pulls a stock's SENS history, computes its actual close-to-close reaction-day return from price data for each announcement, ranks them by move size, and plots the price path (±N trading days) around any selected announcement, plus an averaged event-study path across all "major" announcements.
10. **Rolling Stats & Beta** (`pages/8_🧮_Rolling_Stats_Beta.py`) — reproduces `DoR_Template.xlsx`'s rolling-volatility and beta/correlation sheets: 30/60/90/120-day (or weekly/monthly-scaled) rolling standard deviation of returns, plus rolling beta and correlation against the **JSE All Share** (`^J203.JO`) and **JSE Top 40** (`^J200.JO`) indices over 1/2/5-year windows -- the template originally benchmarked against the S&P 500 and NASDAQ 100, swapped here for the JSE indices.
11. The **Home** page also shows an always-on market breadth summary (pie + sector bar chart, Mega/Large/Mid-cap subset, cached 30 min) so there's a true at-a-glance summary view without a separate click-through.
12. **Relative Performance** (`pages/9_🔀_Relative_Performance.py`) — Koyfin-style normalized (rebased to 0%) performance comparison, in three tabs: whole GICS sectors against each other, industries within one sector (e.g. Banks vs Life Insurance vs the whole Financials sector), and individual stocks within one industry. Every tab can also overlay JSE benchmark indices, has the same MTD/1M/QTD/6M/YTD/1Y/3Y/5Y/10Y/MAX timeframe buttons as the reference screenshots, and a sortable, colour-coded Performance Rankings table underneath the chart.
13. **Pairs Trade** (`pages/10_⚖️_Pairs_Trade.py`) — pick any two stocks (plus optional extra overlay lines) for a pairs-trade workup: normalized performance overlay, price-ratio (spread) chart, a price-vs-price scatter plot (coloured by chronological order, with a linear fit line and correlation) to see how tightly the two actually move together, rolling correlation, rolling z-score of the spread (±2 bands flag stretched territory), and an Engle-Granger cointegration test with a mean-reversion half-life estimate (computed over the last 5 years, regardless of the chart's own timeframe).
14. The **Charts** page now shows a period-returns strip (1D / WTD / MTD / QTD / YTD / 1Y / 3Y / 5Y / 10Y / MAX) for the selected stock, pulled from as much daily history as Yahoo has, independent of whichever period/interval is picked for the candlestick chart itself.

### A note on sector/industry benchmark indices (Relative Performance page)

There's no free official feed for the ~30+ narrower FTSE/JSE sector and industry indices shown on sites like investing.com, and investing.com itself blocks scraping aggressively, so it isn't used as a source here. Instead, `src/relative_performance.py` keeps a small best-effort candidate list of Yahoo Finance tickers for a handful of sectors/industries (assembled via web research, **not** live-verified from this dev sandbox), and for everything else -- or if a candidate ticker fails to return data on your machine -- it automatically falls back to a **constructed index**: the equal-weighted average return of that sector/industry's actual constituent stocks in your JSE universe. Every line in the app is labeled with which kind it is (a real Yahoo ticker, or "Constructed (N stocks, equal-weighted)"), and `scripts/test_data_connection.py` has a dedicated block that tells you which candidate tickers actually work from your machine. Edit the candidate dictionaries in `src/relative_performance.py` any time you confirm a better ticker.

## Setup

```bash
cd jse_analyzer
pip install -r requirements.txt

# confirm your machine can reach Yahoo Finance (the app was built in a
# sandboxed dev environment with no internet access, so this was never
# live-tested end to end — run this first)
python3 scripts/test_data_connection.py

# confirm SENS scraping (Sharenet) and news (Google News RSS) work too
python3 scripts/test_sens_connection.py

# set your own login password (do this before using the app for real)
python3 scripts/set_password.py admin "YourNewPassword"

streamlit run app.py
```

The app opens at `http://localhost:8501`. Log in, then use the sidebar to move between pages.

## How the data works

- **Prices**: pulled from Yahoo Finance via `yfinance`, using `.JO`-suffixed tickers (e.g. `NPN.JO`). Coverage is good for the ~150 most liquid JSE names and gets patchier for micro-caps — the app skips (never crashes on) tickers with no data, and `scripts/test_data_connection.py` will show you where the gaps are on your machine.
- **Caching**: every price series fetched is cached to `data/cache/*.parquet` for 6 hours, and batch requests are chunked (40 tickers at a time, with a short pause between chunks) to avoid tripping Yahoo's rate limits. The cache always stores the **fullest available history** per ticker regardless of which page asked for it -- a page that only needs 2 years of data gets a 2-year slice of that same cached history, rather than a separate, shorter fetch -- so a short-period request from one page can never leave a stale, truncated cache for a later page that wants more years of data. Delete `data/cache/` any time to force a clean refetch.
- **Universe list**: `data/jse_universe_raw.csv` (ticker/name/market cap, sourced from a JSE-listed-companies screener in September 2026) is merged with `data/jse_sector_map.csv` (a hand-built GICS-11 sector/industry classification) by `scripts/build_universe.py` to produce `data/jse_universe.csv`, which the app actually reads. **The sector/industry mapping is a best-effort classification** — I don't have a live JSE/GICS data feed, so I classified all 259 names from general knowledge of these companies. It's a reasonable starting point, not an official source — treat it as editable: open `data/jse_sector_map.csv`, fix any entries you know to be wrong, and rerun `python3 scripts/build_universe.py`.
- **Market-cap tiers**: Mega (>R200bn) / Large (R50–200bn) / Mid (R10–50bn) / Small (R2–10bn) / Micro (<R2bn). These are JSE-calibrated buckets chosen to split the 259-stock universe sensibly — they are **not** the same absolute cutoffs used for US mega/large/mid/small/micro caps (the JSE is a much smaller market outside a handful of dual-listed giants like BHP, AB InBev, Richemont). Edit the `TIERS` list in `scripts/build_universe.py` if you'd rather use different bands, then rerun it.
- **SENS**: scraped from `https://www.sharenet.co.za/v3/sens.php` (public, no login required for the headline list). There is no official free JSE SENS API, so this is inherently fragile -- if Sharenet changes their page markup, `src/sens_news.py:fetch_sens` will need a small patch (it's written defensively: on any parsing failure it returns an empty result rather than crashing the page). `scripts/test_sens_connection.py` tells you immediately if this has broken.
- **News**: Google News RSS search (`news.google.com/rss/search`), scoped with South Africa language/region parameters. No API key needed; this endpoint has been stable for years but isn't an official Google API either.

## Roadmap

All three planned phases are built. Natural next steps if you want to keep going: swap the free yfinance/Sharenet/Google-News data sources for a paid vendor if coverage or reliability becomes a problem (see "How the data works" above), add a scheduled background refresh so the app doesn't re-fetch on every page load, or add portfolio/watchlist tracking on top of the screener.

## Project layout

```
app.py                     Home page (login gate lives here + on every page)
pages/                     Streamlit auto-discovers these as sidebar nav
  1_📊_Screener.py
  2_📈_Charts.py
  3_🌡️_Market_Breadth.py
  4_📉_Distribution_of_Returns.py
  5_📐_ATR_Percent.py
  6_📰_SENS_News.py
  7_🗓️_Event_Study.py
  8_🧮_Rolling_Stats_Beta.py
  9_🔀_Relative_Performance.py
  10_⚖️_Pairs_Trade.py
src/
  auth.py                  Login gate + password hashing
  common.py                Shared page bootstrap (theme, login, sidebar)
  data.py                  yfinance fetch + disk caching
  indicators.py            SMA/RSI/MACD/Bollinger + ATR%/returns/distribution/event-study/period-return stats
  relative_performance.py  Sector/industry/index normalized-performance lines (real + constructed)
  pairs.py                 Pairs-trade stats: spread, rolling correlation/z-score, cointegration, half-life
  sens_news.py             SENS scraping (Sharenet) + news (Google News RSS)
  theme.py                 Dark Koyfin-style CSS + Plotly template
data/
  jse_universe.csv          <- the file the app reads
  jse_universe_raw.csv       (scraped rank/ticker/market cap)
  jse_sector_map.csv         (hand-curated GICS sector/industry, editable)
  cache/                     (gitignored -- price history cache)
scripts/
  build_universe.py         Rebuild jse_universe.csv after editing the raw/sector CSVs
  set_password.py           Change login credentials
  test_data_connection.py   Sanity-check yfinance connectivity from your machine
  test_sens_connection.py   Sanity-check SENS scraping + news RSS from your machine
  debug_sens_html.py        Diagnostic: dumps the raw SENS page structure if headlines look wrong/blank
```

## Known limitations

- Built and tested in a network-sandboxed environment: all Streamlit UI logic was verified with `streamlit.testing.v1.AppTest` against mocked price/SENS/news data (including clicking through buttons, cycling every timeframe/sector filter, and picking specific announcements in the Event Study page), and the SMA/RSI/MACD/Bollinger/ATR%/returns/event-window math was checked against synthetic data — but no call has actually round-tripped to Yahoo Finance, Sharenet, or Google News yet. Run both `scripts/test_data_connection.py` and `scripts/test_sens_connection.py` first thing.
- Micro/nano-cap JSE names, dual-class BEE shares, and a few dormant-listing tickers may simply have no Yahoo Finance data — the app is written to skip these gracefully rather than error out, but breadth/screener numbers for the "All JSE stocks" scope will undercount by however many tickers Yahoo doesn't carry.
- SENS and news are unofficial scrapes of public pages (see "How the data works" above) — treat them as best-effort. Both fail soft (empty result + a message) rather than crashing the app.
- Single/multi-user password login only — not intended as hardened security. Fine for a locally-run personal tool.
