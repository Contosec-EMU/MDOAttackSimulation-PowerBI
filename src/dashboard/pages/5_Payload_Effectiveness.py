"""Payload Effectiveness — predicted vs actual compromise rates and payload attributes."""

import streamlit as st
import pandas as pd

from components.layout import load_css, page_header, page_footer, no_data_warning
from components.metrics import metric_row, section_header
from components.charts import bar_chart, treemap_chart, scatter_chart
from components.filters import multiselect_filter, apply_filters
from data.loader import load_table

st.set_page_config(page_title="Payload Effectiveness", page_icon="📦", layout="wide")
load_css()
page_header("📦 Payload Effectiveness", "Compare predicted vs actual compromise rates and explore payload attributes.")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
payloads = load_table("payloads")
simulations = load_table("simulations")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    technique_sel = multiselect_filter(payloads, "technique", "Technique")

payloads = apply_filters(payloads, filters={"technique": technique_sel})

# ---------------------------------------------------------------------------
# Join payloads with simulations to get actual compromise rates
# ---------------------------------------------------------------------------
if (
    not payloads.empty
    and not simulations.empty
    and "payloadId" in payloads.columns
    and "payloadId" in simulations.columns
):
    sim_agg = simulations.groupby("payloadId", dropna=False).agg(
        totalUsers=("reportTotalUserCount", "sum"),
        totalCompromised=("reportCompromisedCount", "sum"),
        simulation_count=("simulationId", "count"),
    ).reset_index()
    sim_agg["actual_rate"] = sim_agg.apply(
        lambda r: r["totalCompromised"] / r["totalUsers"] if r["totalUsers"] > 0 else 0,
        axis=1,
    )
    payload_sim = payloads.merge(sim_agg, on="payloadId", how="left")
    payload_sim["actual_rate"] = payload_sim["actual_rate"].fillna(0)
    payload_sim["simulation_count"] = payload_sim["simulation_count"].fillna(0).astype(int)
else:
    payload_sim = payloads.copy()
    if not payload_sim.empty:
        payload_sim["actual_rate"] = 0
        payload_sim["simulation_count"] = 0
        payload_sim["totalUsers"] = 0
        payload_sim["totalCompromised"] = 0

# ---------------------------------------------------------------------------
# KPI: Actual vs Predicted variance
# ---------------------------------------------------------------------------
if not payload_sim.empty and "predictedCompromiseRate" in payload_sim.columns:
    avg_predicted = payload_sim["predictedCompromiseRate"].mean()
    avg_actual = payload_sim["actual_rate"].mean()
    variance = avg_actual - avg_predicted
else:
    variance = 0

metric_row([
    {"label": "Actual vs Predicted Variance",
     "value": f"{variance:+.1%}",
     "help": "Difference between mean actual compromise rate and mean predicted rate"},
])

# ---------------------------------------------------------------------------
# Bar chart: Predicted vs Actual by payload
# ---------------------------------------------------------------------------
section_header("Predicted vs Actual Compromise Rates")
if payload_sim.empty or "predictedCompromiseRate" not in payload_sim.columns:
    no_data_warning("payloads")
else:
    chart_df = payload_sim[["displayName", "predictedCompromiseRate", "actual_rate"]].copy()
    melted = chart_df.melt(
        id_vars=["displayName"],
        value_vars=["predictedCompromiseRate", "actual_rate"],
        var_name="Metric",
        value_name="Rate",
    )
    melted["Metric"] = melted["Metric"].replace({
        "predictedCompromiseRate": "Predicted",
        "actual_rate": "Actual",
    })
    fig = bar_chart(melted, x="displayName", y="Rate", color="Metric",
                    title="Predicted vs Actual Compromise Rate by Payload")
    fig.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Treemap: Payloads by theme
# ---------------------------------------------------------------------------
section_header("Payloads by Theme")
if payload_sim.empty or "theme" not in payload_sim.columns:
    no_data_warning("payloads")
else:
    tree_df = payload_sim[payload_sim["simulation_count"] > 0].copy() if "simulation_count" in payload_sim.columns else payload_sim.copy()
    if tree_df.empty:
        st.info("No payloads with associated simulations to display.")
    else:
        fig = treemap_chart(
            tree_df, path=["theme", "displayName"], values="simulation_count",
            title="Payloads Grouped by Theme (sized by simulation count)",
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Payload details table
# ---------------------------------------------------------------------------
section_header("Payload Details")
if payloads.empty:
    no_data_warning("payloads")
else:
    table_cols = ["displayName", "technique", "theme", "complexity", "predictedCompromiseRate"]
    available = [c for c in table_cols if c in payloads.columns]
    st.dataframe(payloads[available], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Scatter: complexity vs actual compromise rate
# ---------------------------------------------------------------------------
section_header("Complexity vs Actual Compromise Rate")
if payload_sim.empty or "complexity" not in payload_sim.columns:
    no_data_warning("payloads")
else:
    scatter_df = payload_sim[payload_sim["totalUsers"] > 0].copy() if "totalUsers" in payload_sim.columns else payload_sim.copy()
    if scatter_df.empty:
        st.info("No payloads with user data to chart.")
    else:
        fig = scatter_chart(
            scatter_df, x="complexity", y="actual_rate",
            title="Payload Complexity vs Actual Compromise Rate",
            size="totalUsers" if "totalUsers" in scatter_df.columns else None,
            hover_name="displayName" if "displayName" in scatter_df.columns else None,
        )
        st.plotly_chart(fig, use_container_width=True)

page_footer()
