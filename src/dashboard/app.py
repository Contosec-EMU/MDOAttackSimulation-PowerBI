"""MDO Attack Simulation Training — Landing Page."""

import streamlit as st

st.set_page_config(
    page_title="MDO Attack Simulation Training",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
with open("theme/style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# -- Sidebar branding --------------------------------------------------------
st.sidebar.markdown(
    '<div class="sidebar-brand">'
    '<span class="sidebar-brand-icon">&#x1F6E1;&#xFE0E;</span>'
    '<span class="sidebar-brand-title">MDO Attack Simulation</span>'
    "</div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    '<p class="sidebar-subtitle">Security Training Analytics</p>',
    unsafe_allow_html=True,
)
st.sidebar.divider()

# -- Hero header --------------------------------------------------------------
st.markdown(
    '<div class="hero-header">'
    "<h1>MDO Attack Simulation Training</h1>"
    "<p>Monitor phishing simulation performance, user risk, training compliance, "
    "and payload effectiveness across your organization.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# -- Navigation cards ---------------------------------------------------------
NAV_SECTIONS = [
    {
        "title": "Executive Dashboard",
        "desc": "Organization-wide KPIs, compromise trends, and simulation "
                "success rates at a glance.",
        "page": "pages/1_Executive_Dashboard.py",
        "icon": "&#x2261;",
    },
    {
        "title": "Simulation Analysis",
        "desc": "Drill into individual simulation campaigns, techniques used, "
                "and comparative results.",
        "page": "pages/2_Simulation_Analysis.py",
        "icon": "&#x25C8;",
    },
    {
        "title": "User Risk Profile",
        "desc": "Identify high-risk users, repeat offenders, and departments "
                "that need additional training.",
        "page": "pages/3_User_Risk_Profile.py",
        "icon": "&#x2666;&#xFE0E;",
    },
    {
        "title": "Training Compliance",
        "desc": "Track assignment completion rates, overdue trainings, and "
                "compliance by department.",
        "page": "pages/4_Training_Compliance.py",
        "icon": "&#x2713;",
    },
    {
        "title": "Payload Effectiveness",
        "desc": "Compare social-engineering payload types, click-through rates, "
                "and credential harvesting success.",
        "page": "pages/5_Payload_Effectiveness.py",
        "icon": "&#x29BF;",
    },
]

cols = st.columns(3)
for idx, section in enumerate(NAV_SECTIONS):
    with cols[idx % 3]:
        st.markdown(
            '<div class="nav-card">'
            f'<div class="nav-card-icon">{section["icon"]}</div>'
            f'<div class="nav-card-title">{section["title"]}</div>'
            f'<div class="nav-card-desc">{section["desc"]}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.page_link(section["page"], label=f"Open {section['title']}")

# -- Getting started notice ---------------------------------------------------
st.markdown("---")
st.markdown(
    '<div class="getting-started">'
    "<strong>Getting started</strong> &mdash; "
    "This dashboard reads data from your ADLS Gen2 storage account. "
    "Ensure the Azure Function has run at least once to populate the "
    "Parquet files before exploring the pages above."
    "</div>",
    unsafe_allow_html=True,
)
