"""Executive Dashboard — high-level KPIs and trends."""

import streamlit as st
import pandas as pd

from components.layout import load_css, page_header, page_footer, no_data_warning
from components.metrics import metric_row, section_header
from components.charts import line_chart, donut_chart
from components.filters import date_range_filter, apply_filters
from data.loader import load_table

st.set_page_config(page_title="Executive Dashboard", page_icon="📊", layout="wide")
load_css()
page_header("📊 Executive Dashboard", "Organization-wide attack simulation KPIs and trends.")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
simulations = load_table("simulations")
simulation_users = load_table("simulationUsers")
repeat_offenders = load_table("repeatOffenders")
training_coverage = load_table("trainingUserCoverage")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    date_range = date_range_filter(simulations, "launchDateTime", "Launch Date Range")

simulations = apply_filters(simulations, date_column="launchDateTime", date_range=date_range)

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
total_users = len(simulation_users)
compromised_users = simulation_users["isCompromised"].sum() if "isCompromised" in simulation_users.columns else 0
compromise_rate = compromised_users / total_users if total_users > 0 else 0

assigned_total = training_coverage["assignedTrainingsCount"].sum() if "assignedTrainingsCount" in training_coverage.columns else 0
completed_total = training_coverage["completedTrainingsCount"].sum() if "completedTrainingsCount" in training_coverage.columns else 0
training_completion = completed_total / assigned_total if assigned_total > 0 else 0

repeat_count = 0
if not repeat_offenders.empty and "repeatOffenceCount" in repeat_offenders.columns:
    repeat_count = int((repeat_offenders["repeatOffenceCount"] > 1).sum())

active_sims = 0
if not simulations.empty:
    mask = simulations["status"] == "succeeded"
    if "launchDateTime" in simulations.columns:
        mask = mask & simulations["launchDateTime"].notna()
    active_sims = int(mask.sum())

metric_row([
    {"label": "Compromise Rate", "value": f"{compromise_rate:.1%}"},
    {"label": "Training Completion", "value": f"{training_completion:.1%}"},
    {"label": "Repeat Offenders", "value": f"{repeat_count:,.0f}"},
    {"label": "Active Simulations", "value": f"{active_sims:,.0f}"},
])

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
section_header("Trends & Breakdown")
col_left, col_right = st.columns(2)

with col_left:
    if simulation_users.empty or "compromisedDateTime" not in simulation_users.columns:
        no_data_warning("simulationUsers")
    else:
        compromised = simulation_users[simulation_users["isCompromised"] == True].copy()  # noqa: E712
        if compromised.empty:
            st.info("No compromised user records to chart.")
        else:
            compromised["month"] = pd.to_datetime(
                compromised["compromisedDateTime"], errors="coerce"
            ).dt.to_period("M").astype(str)
            monthly = compromised.groupby("month").size().reset_index(name="compromised_count")
            fig = line_chart(monthly, x="month", y="compromised_count",
                             title="Monthly Compromised Users")
            st.plotly_chart(fig, use_container_width=True)

with col_right:
    if simulations.empty or "attackType" not in simulations.columns:
        no_data_warning("simulations")
    else:
        attack_dist = simulations.groupby("attackType").size().reset_index(name="count")
        fig = donut_chart(attack_dist, names="attackType", values="count",
                          title="Simulations by Attack Type")
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Top repeat offenders table
# ---------------------------------------------------------------------------
section_header("Top Repeat Offenders")
if repeat_offenders.empty:
    no_data_warning("repeatOffenders")
else:
    display_cols = ["displayName", "email", "repeatOffenceCount"]
    available = [c for c in display_cols if c in repeat_offenders.columns]
    top10 = repeat_offenders.nlargest(10, "repeatOffenceCount")[available]
    st.dataframe(top10, use_container_width=True, hide_index=True)

page_footer()
