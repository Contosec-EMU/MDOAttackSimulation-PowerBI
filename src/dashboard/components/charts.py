"""Plotly chart wrappers with Fluent Design styling."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Fluent Design color palette
COLORS = {
    "primary": "#0078d4",
    "primary_dark": "#005a9e",
    "primary_light": "#deecf9",
    "success": "#107c10",
    "warning": "#ffb900",
    "danger": "#d13438",
    "neutral": "#605e5c",
    "background": "#ffffff",
    "text": "#323130",
}

FLUENT_PALETTE = [
    "#0078d4", "#005a9e", "#2b88d8", "#71afe5",
    "#107c10", "#bad80a", "#ffb900", "#d83b01",
    "#e3008c", "#5c2d91", "#00188f", "#008272",
]

LAYOUT_DEFAULTS = dict(
    font=dict(family="Segoe UI, sans-serif", color=COLORS["text"]),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
)


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str | None = None,
    horizontal: bool = False,
    **kwargs,
) -> go.Figure:
    """Create a styled bar chart."""
    if horizontal:
        fig = px.bar(df, x=y, y=x, orientation="h", color=color,
                     color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    else:
        fig = px.bar(df, x=x, y=y, color=color,
                     color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_traces(marker_line_width=0)
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str | None = None,
    **kwargs,
) -> go.Figure:
    """Create a styled line chart."""
    fig = px.line(df, x=x, y=y, color=color,
                  color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_traces(line_width=2.5)
    return fig


def donut_chart(
    df: pd.DataFrame,
    names: str,
    values: str,
    title: str = "",
    **kwargs,
) -> go.Figure:
    """Create a styled donut chart."""
    fig = px.pie(df, names=names, values=values, hole=0.5,
                 color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_traces(textposition="outside", textinfo="label+percent")
    return fig


def scatter_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    size: str | None = None,
    color: str | None = None,
    hover_name: str | None = None,
    **kwargs,
) -> go.Figure:
    """Create a styled scatter chart."""
    fig = px.scatter(df, x=x, y=y, size=size, color=color, hover_name=hover_name,
                     color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    return fig


def treemap_chart(
    df: pd.DataFrame,
    path: list[str],
    values: str,
    title: str = "",
    color: str | None = None,
    **kwargs,
) -> go.Figure:
    """Create a styled treemap chart."""
    fig = px.treemap(df, path=path, values=values, color=color,
                     color_discrete_sequence=FLUENT_PALETTE, title=title, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    return fig


def stacked_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: list[str],
    title: str = "",
    labels: dict | None = None,
    **kwargs,
) -> go.Figure:
    """Create a styled stacked bar chart from multiple y columns."""
    melted = df.melt(id_vars=[x], value_vars=y, var_name="Category", value_name="Count")
    fig = px.bar(melted, x=x, y="Count", color="Category", barmode="stack",
                 color_discrete_sequence=FLUENT_PALETTE, title=title,
                 labels=labels or {}, **kwargs)
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_traces(marker_line_width=0)
    return fig
