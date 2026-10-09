"""Research (not yet built)."""
import streamlit as st

from core.ui import page_footer, page_header, require_project

require_project()
page_header("Research")
st.info("This tool is being built and will be available in a later release.")
page_footer()
