"""Page layout helpers — header, footer, page setup."""

from __future__ import annotations

import streamlit as st


def page_header(title: str, description: str) -> None:
    """Render a page header with an accent-bar underline."""
    st.markdown(
        '<div class="page-header">'
        f"<h1>{title}</h1>"
        f"<p>{description}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def page_footer() -> None:
    """Render a subtle page footer."""
    st.markdown(
        '<div class="page-footer">'
        "<p>MDO Attack Simulation Training &mdash; "
        "Customize visuals and layout to match your organization's "
        "reporting standards.</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def no_data_warning(table_name: str) -> None:
    """Show a warning when a table has no data."""
    st.warning(
        f"No data available for **{table_name}**. "
        "Make sure the Azure Function has run and produced data for this table.",
    )


def load_css() -> None:
    """Load the custom Fluent Design CSS."""
    try:
        with open("theme/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass
