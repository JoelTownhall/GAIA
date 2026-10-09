"""Shared page chrome: styles, header, disclaimer, current-project handling."""
from __future__ import annotations

import streamlit as st

from core.framework import load_framework
from core.project import Project
from core.storage import ProjectStore, get_store

APP_NAME = "IA Navigator"

DISCLAIMER = (
    "IA Navigator is a drafting aid. It is not advice from the Office of Impact Analysis "
    "and does not assess Impact Analyses. Content you enter is sent to the Claude API and "
    "stored in your project folder. Do not enter Cabinet-in-confidence or "
    "security-classified material."
)

_CSS = """
<style>
.block-container { padding-top: 2rem; max-width: 1100px; }
h1, h2, h3 { color: #1f4e79; letter-spacing: -0.01em; }
.ian-banner {
    border-left: 4px solid #1f4e79; background: #f4f6f9;
    padding: 10px 14px; margin: 0 0 18px 0; font-size: 0.9rem; color: #33415c;
}
.ian-step {
    border: 1px solid #dce3ea; border-radius: 8px; padding: 14px 16px; margin-bottom: 10px;
}
.ian-step .num { color: #1f4e79; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
.ian-step .title { font-weight: 600; font-size: 1.05rem; margin: 2px 0 6px 0; }
.ian-step .summary { color: #33415c; font-size: 0.92rem; }
.ian-tag {
    display: inline-block; font-size: 0.75rem; padding: 1px 8px; border-radius: 10px;
    background: #e8eef5; color: #1f4e79; margin-right: 6px;
}
.ian-footer { color: #5b6b80; font-size: 0.8rem; margin-top: 32px; }
@media (max-width: 768px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
}
</style>
"""


def page_header(title: str, intro: str = "") -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    fw = load_framework()
    st.markdown(
        f'<div class="ian-banner">{fw.meta.title} — effective {fw.meta.effective_from}</div>',
        unsafe_allow_html=True,
    )
    st.title(title)
    if intro:
        st.markdown(intro)


def page_footer(sources: list[str] | None = None) -> None:
    text = DISCLAIMER
    if sources:
        text = "Sources: " + "; ".join(sources) + ". " + text
    st.markdown(f'<div class="ian-footer">{text}</div>', unsafe_allow_html=True)


def current_user_email() -> str:
    """Signed-in user's email when st.login is configured, else empty."""
    try:
        if st.user.is_logged_in:
            return st.user.email or ""
    except Exception:
        pass
    return ""


@st.cache_resource
def store() -> ProjectStore:
    return get_store()


def current_project() -> Project | None:
    project_id = st.session_state.get("project_id")
    if not project_id:
        return None
    try:
        return store().load_project(project_id)
    except Exception:
        st.session_state.pop("project_id", None)
        return None


def require_project() -> Project:
    """Stop the page with a pointer to the project picker if none is open."""
    project = current_project()
    if project is None:
        st.info("Open or create a project first. Everything you produce is saved to its folder.")
        st.page_link("views/home.py", label="Go to projects")
        st.stop()
    return project


def sidebar_project_badge() -> None:
    project = current_project()
    with st.sidebar:
        if project:
            st.caption("Current project")
            st.markdown(f"**{project.name}**")
            if project.agency:
                st.caption(project.agency)
        else:
            st.caption("No project open")
