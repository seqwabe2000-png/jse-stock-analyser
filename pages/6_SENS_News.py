import streamlit as st

from src import data, sens_news
from src.common import bootstrap

bootstrap("SENS & News", "📰")

st.title("📰 SENS Announcements & News")
st.caption(
    "Best-effort feed -- SENS headlines are scraped from Sharenet's public SENS page (no free official "
    "JSE SENS API exists) and news comes from Google News. If a section below comes up empty, run "
    "`python3 scripts/test_sens_connection.py` to check whether the source is reachable/still working."
)

universe = data.load_universe()


def _matches(uni, query):
    q = query.strip().lower()
    if not q:
        return uni
    return uni[
        uni["symbol"].str.lower().str.contains(q, regex=False)
        | uni["name"].str.lower().str.contains(q, regex=False)
    ]


c1, c2, c3, c4 = st.columns([1.5, 1.3, 2, 1])
with c1:
    search_query = st.text_input(
        "🔍 Search stock (name or ticker)", placeholder="e.g. Naspers or NPN", key="sens_search"
    )
with c2:
    sector_filter = st.selectbox("Sector filter", ["All sectors"] + sorted(universe["gics_sector"].unique()))
    stock_universe = universe if sector_filter == "All sectors" else universe[universe["gics_sector"] == sector_filter]

filtered = _matches(stock_universe, search_query)
if search_query and filtered.empty:
    broader = _matches(universe, search_query)
    if not broader.empty:
        st.caption(f"No matches for \"{search_query}\" in {sector_filter} -- showing matches across all sectors instead.")
        filtered = broader

with c3:
    label_to_row = {f"{r['symbol']} — {r['name']}": r for _, r in filtered.iterrows()}
    if not label_to_row:
        st.warning(f"No stocks match \"{search_query}\"." if search_query else "No stocks in this sector.")
        st.stop()
    choice = st.selectbox("Stock", options=sorted(label_to_row.keys()))
    row = label_to_row[choice]
with c4:
    days = st.slider("Lookback (days)", 7, 180, 60, step=7)


@st.cache_data(ttl=900, show_spinner=False)
def _cached_sens(symbol, days):
    return sens_news.fetch_sens(symbol, days=days)


@st.cache_data(ttl=900, show_spinner=False)
def _cached_news(query, days):
    return sens_news.fetch_news(query, days=days)


tab_sens, tab_company_news, tab_sector_news = st.tabs(
    ["📢 SENS Announcements", "📰 Company News", f"🏷️ {row['gics_sector']} Sector News"]
)

with tab_sens:
    with st.spinner("Fetching SENS announcements..."):
        sens_df = _cached_sens(row["symbol"], days)
    if sens_df.empty:
        st.info(f"No SENS announcements found for {row['symbol']} in the last {days} days (or the source is unreachable).")
    else:
        st.caption(f"{len(sens_df)} announcement(s) in the last {days} days. Click a row's link to open the full announcement.")
        display = sens_df.copy()
        display["Date"] = display["datetime"].dt.strftime("%Y-%m-%d %H:%M")
        display["Move %"] = display["pct_move"].map(lambda x: f"{x:+.2f}%" if x == x and x is not None else "—")
        display = display.rename(columns={"headline": "Headline", "code": "Code", "url": "Link"})
        display = display[["Date", "Code", "Headline", "Move %", "Link"]]
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=min(700, 60 + 42 * len(display)),
            column_config={
                "Date": st.column_config.TextColumn(width="small"),
                "Code": st.column_config.TextColumn(width="small"),
                "Headline": st.column_config.TextColumn(width="large"),
                "Move %": st.column_config.TextColumn(width="small"),
                "Link": st.column_config.LinkColumn(display_text="Open ↗", width="small"),
            },
        )

with tab_company_news:
    with st.spinner("Fetching news..."):
        news_df = _cached_news(f'"{row["name"]}"', days)
    if news_df.empty:
        st.info(f"No recent news found for {row['name']} (or the source is unreachable).")
    else:
        st.caption(f"{len(news_df)} article(s) in the last {days} days.")
        display = news_df.copy()
        display["Date"] = display["published"].map(lambda d: d.strftime("%Y-%m-%d") if d is not None else "—")
        display = display.rename(columns={"title": "Headline", "source": "Source", "link": "Link"})
        display = display[["Date", "Headline", "Source", "Link"]]
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=min(600, 60 + 42 * len(display)),
            column_config={
                "Date": st.column_config.TextColumn(width="small"),
                "Headline": st.column_config.TextColumn(width="large"),
                "Source": st.column_config.TextColumn(width="small"),
                "Link": st.column_config.LinkColumn(display_text="Open ↗", width="small"),
            },
        )

with tab_sector_news:
    with st.spinner("Fetching sector news..."):
        sector_news_df = _cached_news(f'"{row["gics_sector"]}" JSE South Africa', days)
    if sector_news_df.empty:
        st.info(f"No recent {row['gics_sector']} sector news found (or the source is unreachable).")
    else:
        st.caption(f"{len(sector_news_df)} article(s) in the last {days} days.")
        display = sector_news_df.copy()
        display["Date"] = display["published"].map(lambda d: d.strftime("%Y-%m-%d") if d is not None else "—")
        display = display.rename(columns={"title": "Headline", "source": "Source", "link": "Link"})
        display = display[["Date", "Headline", "Source", "Link"]]
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            height=min(600, 60 + 42 * len(display)),
            column_config={
                "Date": st.column_config.TextColumn(width="small"),
                "Headline": st.column_config.TextColumn(width="large"),
                "Source": st.column_config.TextColumn(width="small"),
                "Link": st.column_config.LinkColumn(display_text="Open ↗", width="small"),
            },
        )
