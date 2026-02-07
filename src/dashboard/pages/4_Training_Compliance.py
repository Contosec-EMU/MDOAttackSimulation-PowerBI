"""Training Compliance — completion rates, status by department, and correlation."""

import streamlit as st
import pandas as pd

from components.layout import load_css, page_header, page_footer, no_data_warning
from components.metrics import metric_row, section_header
from components.charts import stacked_bar_chart, scatter_chart
from data.loader import load_table

st.set_page_config(page_title="Training Compliance", page_icon="🎓", layout="wide")
load_css()
page_header("🎓 Training Compliance", "Track training completion rates and their relationship to simulation outcomes.")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
training_cov = load_table("trainingUserCoverage")
trainings = load_table("trainings")
users = load_table("users")
sim_user_cov = load_table("simulationUserCoverage")

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
assigned_total = training_cov["assignedTrainingsCount"].sum() if "assignedTrainingsCount" in training_cov.columns else 0
completed_total = training_cov["completedTrainingsCount"].sum() if "completedTrainingsCount" in training_cov.columns else 0
completion_rate = completed_total / assigned_total if assigned_total > 0 else 0

avg_duration = trainings["durationInMinutes"].mean() if (
    not trainings.empty and "durationInMinutes" in trainings.columns
) else 0

metric_row([
    {"label": "Training Completion Rate", "value": f"{completion_rate:.1%}"},
    {"label": "Avg Training Duration (min)", "value": f"{avg_duration:,.0f}"},
])

# ---------------------------------------------------------------------------
# Join department info
# ---------------------------------------------------------------------------
if not training_cov.empty and not users.empty and "userId" in training_cov.columns and "userId" in users.columns:
    user_dept = users[["userId", "department"]].drop_duplicates(subset=["userId"])
    training_cov = training_cov.merge(user_dept, on="userId", how="left")

# ---------------------------------------------------------------------------
# Stacked bar: training status by department
# ---------------------------------------------------------------------------
section_header("Training Status by Department")
status_cols = ["completedTrainingsCount", "inProgressTrainingsCount", "notStartedTrainingsCount"]
if training_cov.empty or "department" not in training_cov.columns:
    no_data_warning("trainingUserCoverage")
else:
    present = [c for c in status_cols if c in training_cov.columns]
    if present:
        dept_status = training_cov.groupby("department", dropna=False)[present].sum().reset_index()
        fig = stacked_bar_chart(
            dept_status, x="department", y=present,
            title="Training Status by Department",
            labels={
                "completedTrainingsCount": "Completed",
                "inProgressTrainingsCount": "In Progress",
                "notStartedTrainingsCount": "Not Started",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# User training status table
# ---------------------------------------------------------------------------
section_header("User Training Status")
if training_cov.empty:
    no_data_warning("trainingUserCoverage")
else:
    table_cols = ["displayName", "department", "assignedTrainingsCount",
                  "completedTrainingsCount", "notStartedTrainingsCount"]
    available = [c for c in table_cols if c in training_cov.columns]
    st.dataframe(training_cov[available], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Scatter: training completions vs compromises
# ---------------------------------------------------------------------------
section_header("Training vs Compromise Correlation")
if training_cov.empty or sim_user_cov.empty:
    no_data_warning("trainingUserCoverage / simulationUserCoverage")
else:
    join_cols_train = ["userId", "completedTrainingsCount"]
    join_cols_sim = ["userId", "compromisedCount"]
    train_avail = [c for c in join_cols_train if c in training_cov.columns]
    sim_avail = [c for c in join_cols_sim if c in sim_user_cov.columns]
    if "userId" in train_avail and "userId" in sim_avail:
        merged = training_cov[train_avail].merge(sim_user_cov[sim_avail], on="userId", how="inner")
        if merged.empty:
            st.info("No matching user records between training and simulation data.")
        else:
            fig = scatter_chart(
                merged, x="completedTrainingsCount", y="compromisedCount",
                title="Completed Trainings vs Compromises",
            )
            st.plotly_chart(fig, use_container_width=True)

page_footer()
