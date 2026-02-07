"""Simulation Analysis — per-simulation metrics and response breakdown."""

import streamlit as st
import pandas as pd

from components.layout import load_css, page_header, page_footer, no_data_warning
from components.metrics import metric_row, section_header
from components.charts import bar_chart
from components.filters import date_range_filter, multiselect_filter, apply_filters
from data.loader import load_table

st.set_page_config(page_title="Simulation Analysis", page_icon="🔬", layout="wide")
load_css()
page_header("🔬 Simulation Analysis", "Drill into individual simulation performance and response metrics.")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
simulations = load_table("simulations")
simulation_users = load_table("simulationUsers")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    attack_type_sel = multiselect_filter(simulations, "attackType", "Attack Type")
    date_range = date_range_filter(simulations, "launchDateTime", "Launch Date Range")

simulations = apply_filters(
    simulations,
    date_column="launchDateTime",
    date_range=date_range,
    filters={"attackType": attack_type_sel},
)

# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
reported_total = simulations["reportReportedCount"].sum() if "reportReportedCount" in simulations.columns else 0
user_total = simulations["reportTotalUserCount"].sum() if "reportTotalUserCount" in simulations.columns else 0
phish_report_rate = reported_total / user_total if user_total > 0 else 0

metric_row([
    {"label": "Phish Report Rate", "value": f"{phish_report_rate:.1%}",
     "help": "Proportion of targeted users who reported the phish"},
])

# ---------------------------------------------------------------------------
# Simulation data table
# ---------------------------------------------------------------------------
section_header("Simulation Details")
if simulations.empty:
    no_data_warning("simulations")
else:
    table_cols = [
        "displayName", "attackType", "attackTechnique", "launchDateTime",
        "reportTotalUserCount", "reportCompromisedCount", "reportClickCount",
        "reportReportedCount",
    ]
    available = [c for c in table_cols if c in simulations.columns]
    st.dataframe(simulations[available], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
section_header("Simulation Performance")
col_left, col_right = st.columns(2)

with col_left:
    if simulations.empty:
        no_data_warning("simulations")
    else:
        sim_chart = simulations.copy()
        sim_chart["compromise_rate"] = sim_chart.apply(
            lambda r: r["reportCompromisedCount"] / r["reportTotalUserCount"]
            if r.get("reportTotalUserCount", 0) > 0 else 0,
            axis=1,
        )
        fig = bar_chart(sim_chart, x="displayName", y="compromise_rate",
                        title="Compromise Rate per Simulation")
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    if simulations.empty:
        no_data_warning("simulations")
    else:
        response_cols = ["reportCompromisedCount", "reportClickCount", "reportReportedCount"]
        present = [c for c in response_cols if c in simulations.columns]
        if present and "displayName" in simulations.columns:
            melted = simulations.melt(
                id_vars=["displayName"], value_vars=present,
                var_name="Metric", value_name="Count",
            )
            fig = bar_chart(melted, x="displayName", y="Count", color="Metric",
                            title="Response Metrics per Simulation")
            st.plotly_chart(fig, use_container_width=True)

page_footer()
