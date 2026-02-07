"""MDO Attack Simulation Training — Executive Dashboard."""

import streamlit as st

st.set_page_config(
    page_title="MDO Attack Simulation Training",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
with open("theme/style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.sidebar.image(
    "https://img.icons8.com/fluency/48/shield.png",
    width=40,
)
st.sidebar.title("MDO Attack Simulation")
st.sidebar.caption(
    "Starter dashboard — customize to fit your organization's needs."
)

st.title("🛡️ MDO Attack Simulation Training")
st.markdown(
    "Select a page from the sidebar to explore simulation metrics, "
    "user risk profiles, training compliance, and payload effectiveness."
)
st.info(
    "📌 **Getting started:** This dashboard reads data from your ADLS Gen2 "
    "storage account. Make sure the Azure Function has run at least once "
    "to populate the Parquet files.",
    icon="ℹ️",
)
