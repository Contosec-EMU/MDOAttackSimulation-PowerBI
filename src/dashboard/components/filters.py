"""Reusable filter/slicer components for sidebar."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st


def date_range_filter(
    df: pd.DataFrame,
    date_column: str,
    label: str = "Date Range",
) -> tuple[date, date]:
    """Render a date range filter in the sidebar and return (start, end)."""
    if df.empty or date_column not in df.columns:
        today = date.today()
        return today, today

    col = pd.to_datetime(df[date_column], errors="coerce").dropna()
    if col.empty:
        today = date.today()
        return today, today

    min_date = col.min().date()
    max_date = col.max().date()

    return st.sidebar.date_input(
        label,
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )


def multiselect_filter(
    df: pd.DataFrame,
    column: str,
    label: str | None = None,
) -> list[str]:
    """Render a multiselect filter in the sidebar. Returns selected values."""
    if df.empty or column not in df.columns:
        return []

    options = sorted(df[column].dropna().unique().tolist())
    return st.sidebar.multiselect(label or column, options)


def apply_filters(
    df: pd.DataFrame,
    date_column: str | None = None,
    date_range: tuple[date, date] | None = None,
    filters: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Apply date range and column filters to a DataFrame."""
    if df.empty:
        return df

    result = df.copy()

    if date_column and date_range and len(date_range) == 2:
        col = pd.to_datetime(result[date_column], errors="coerce")
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        result = result[col.between(start, end)]

    if filters:
        for col, values in filters.items():
            if values and col in result.columns:
                result = result[result[col].isin(values)]

    return result
