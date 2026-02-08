"""User Risk Profile — department-level risk and individual user analysis."""

import streamlit as st
import pandas as pd

from components.layout import load_css, page_header, page_footer, no_data_warning
from components.metrics import section_header
from components.charts import bar_chart, scatter_chart, line_chart
from components.filters import multiselect_filter, apply_filters
from data.loader import load_table

st.set_page_config(page_title="User Risk Profile", layout="wide")
load_css()
page_header("User Risk Profile", "Analyse user and department-level risk from simulation results.")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
users = load_table("users")
sim_user_cov = load_table("simulationUserCoverage")
repeat_offenders = load_table("repeatOffenders")
sim_user_events = load_table("simulationUserEvents")

# ---------------------------------------------------------------------------
# Join department info onto simulation user coverage
# ---------------------------------------------------------------------------
if not sim_user_cov.empty and not users.empty and "userId" in sim_user_cov.columns and "userId" in users.columns:
    user_dept = users[["userId", "department"]].drop_duplicates(subset=["userId"])
    sim_user_cov = sim_user_cov.merge(user_dept, on="userId", how="left")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    dept_sel = multiselect_filter(sim_user_cov, "department", "Department")

sim_user_cov = apply_filters(sim_user_cov, filters={"department": dept_sel})

# ---------------------------------------------------------------------------
# Charts — department risk & scatter
# ---------------------------------------------------------------------------
section_header("Department Risk & User Scatter")
col_left, col_right = st.columns(2)

with col_left:
    if sim_user_cov.empty or "department" not in sim_user_cov.columns:
        no_data_warning("simulationUserCoverage")
    else:
        dept_agg = sim_user_cov.groupby("department", dropna=False).agg(
            simulationCount=("simulationCount", "sum"),
            compromisedCount=("compromisedCount", "sum"),
        ).reset_index()
        dept_agg["risk_score"] = dept_agg.apply(
            lambda r: r["compromisedCount"] / r["simulationCount"] * 100
            if r["simulationCount"] > 0 else 0,
            axis=1,
        )
        fig = bar_chart(dept_agg, x="department", y="risk_score",
                        title="Department Risk Score (% Compromised)", horizontal=True)
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    if sim_user_cov.empty:
        no_data_warning("simulationUserCoverage")
    else:
        fig = scatter_chart(
            sim_user_cov, x="simulationCount", y="compromisedCount",
            title="Simulations vs Compromises per User",
            hover_name="displayName" if "displayName" in sim_user_cov.columns else None,
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# User details table
# ---------------------------------------------------------------------------
section_header("User Details")
if sim_user_cov.empty:
    no_data_warning("simulationUserCoverage")
else:
    detail_cols = ["displayName", "department", "simulationCount", "compromisedCount", "clickCount"]
    available = [c for c in detail_cols if c in sim_user_cov.columns]
    st.dataframe(sim_user_cov[available], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Events over time
# ---------------------------------------------------------------------------
section_header("Simulation Events Over Time")
if sim_user_events.empty or "eventDateTime" not in sim_user_events.columns:
    no_data_warning("simulationUserEvents")
else:
    events = sim_user_events.copy()
    events["month"] = pd.to_datetime(
        events["eventDateTime"], errors="coerce"
    ).dt.to_period("M").astype(str)
    monthly = events.groupby("month").size().reset_index(name="event_count")
    fig = line_chart(monthly, x="month", y="event_count", title="Events per Month")
    st.plotly_chart(fig, use_container_width=True)

page_footer()
