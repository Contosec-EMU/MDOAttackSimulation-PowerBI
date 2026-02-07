"""Reusable metric card and KPI components."""

from __future__ import annotations

import streamlit as st


def metric_row(metrics: list[dict]) -> None:
    """Render a row of KPI metric cards.

    Args:
        metrics: List of dicts with keys: label, value, delta (optional), help (optional)
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        col.metric(
            label=m["label"],
            value=m["value"],
            delta=m.get("delta"),
            help=m.get("help"),
        )


def section_header(title: str, description: str | None = None) -> None:
    """Render a section header with optional description."""
    st.markdown(f"## {title}")
    if description:
        st.caption(description)
