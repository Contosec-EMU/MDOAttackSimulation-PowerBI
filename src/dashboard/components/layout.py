"""Page layout helpers — header, footer, page setup."""

from __future__ import annotations

import streamlit as st


def page_header(title: str, description: str) -> None:
    """Render a consistent page header."""
    st.title(title)
    st.caption(description)
    st.divider()


def page_footer() -> None:
    """Render a consistent page footer."""
    st.divider()
    st.caption(
        "💡 This is a starter dashboard — customize visuals and layout "
        "to match your organization's reporting standards."
    )


def no_data_warning(table_name: str) -> None:
    """Show a warning when a table has no data."""
    st.warning(
        f"No data available for **{table_name}**. "
        "Make sure the Azure Function has run and produced data for this table.",
        icon="⚠️",
    )


def load_css() -> None:
    """Load the custom Fluent Design CSS."""
    try:
        with open("theme/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass
