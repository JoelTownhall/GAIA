"""IA Navigator — entry point and navigation."""
import streamlit as st

from core.ui import APP_NAME, sidebar_project_badge

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")

pages = {
    "Projects": [
        st.Page("views/home.py", title="Projects", default=True),
        st.Page("views/project_home.py", title="Project overview"),
    ],
    "Work on your IA": [
        st.Page("views/research.py", title="Research"),
        st.Page("views/general_advice.py", title="General advice"),
        st.Page("views/self_assessment.py", title="Self-assessment"),
        st.Page("views/burden_estimate.py", title="Burden estimate"),
        st.Page("views/draft_export.py", title="Draft and export"),
    ],
    "Reference": [
        st.Page("views/framework_library.py", title="Framework library"),
    ],
}

nav = st.navigation(pages)
sidebar_project_badge()
nav.run()
