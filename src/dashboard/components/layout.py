"""Page layout helpers — header, footer, page setup."""

from __future__ import annotations

import streamlit as st

from data.loader import get_load_error


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
    """Show a warning when a table has no data, with actual error if available."""
    error = get_load_error(table_name)
    if error:
        st.error(
            f"**Failed to load {table_name}:** {error}\n\n"
            "Check that the dashboard's managed identity has "
            "Storage Blob Data Reader on the storage account, "
            "and that the Azure Function has run at least once.",
        )
    else:
        st.warning(
            f"No data available for **{table_name}**. "
            "Make sure the Azure Function has run at least once "
            "to populate data in ADLS Gen2.",
        )


def load_css() -> None:
    """Load the custom Fluent Design CSS."""
    try:
        with open("theme/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass
