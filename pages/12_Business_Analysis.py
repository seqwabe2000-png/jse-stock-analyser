import streamlit as st

from src import business_analysis as ba
from src import data
from src.common import bootstrap

bootstrap("Business Analysis", "🏢")

st.title("🏢 Business Analysis")
st.caption(
    "Builds a deep, 28-question research prompt for a JSE-listed company -- business model, "
    "financials, valuation, moat, options market, credit, and more. This tab doesn't run the "
    "research itself; it hands you the finished prompt to paste into your own Claude.ai chat "
    "(free plan works fine), which does the live web research and can hand you back a "
    "downloadable Word document -- no API key, no cost, nothing to configure."
)

# --------------------------------------------------------------------------
# Company selection
# --------------------------------------------------------------------------
universe = data.load_universe()
label_to_name = {f"{r['symbol']} — {r['name']}": r["name"] for _, r in universe.iterrows()}

c1, c2 = st.columns([2, 2])
with c1:
    picked = st.selectbox(
        "Pick a JSE stock (optional)",
        options=["(type a company name/ticker below instead)"] + sorted(label_to_name.keys()),
        key="ba_picked",
        help="Remembers your last pick on this page -- switching to another page and back won't reset it.",
    )
with c2:
    # Typing directly is remembered too (key="ba_company") -- but picking a
    # new stock from the dropdown should still overwrite it, so that only
    # happens when the dropdown pick itself actually changes, not on every
    # rerun (which would otherwise stomp on anything typed by hand).
    if st.session_state.get("ba_last_picked") != picked:
        st.session_state["ba_last_picked"] = picked
        st.session_state["ba_company"] = label_to_name.get(picked, "")
    company = st.text_input(
        "Company name / ticker to analyze",
        placeholder="e.g. Capitec Bank Holdings, or a non-JSE company",
        key="ba_company",
    )

if company.strip():
    prompt = ba.build_prompt(company.strip())

    st.subheader("Your research prompt")
    st.caption("Click the copy icon in the top-right corner of the box below.")
    st.code(prompt, language=None, wrap_lines=True)

    b1, b2 = st.columns([1, 3])
    with b1:
        st.link_button("Open Claude.ai ↗", "https://claude.ai/new", width="stretch")
    with b2:
        st.caption(
            "Paste the copied prompt into a new chat there and send it. It'll take a couple of "
            "minutes since it's doing real research with several web searches -- that's normal."
        )
else:
    st.info("Pick a stock above, or type a company name/ticker, to generate its research prompt.")
