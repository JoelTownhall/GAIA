"""Settings lookup: Streamlit secrets first, then environment variables."""
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content"
REFERENCE_DIR = REPO_ROOT / "reference_docs" / "oia_2026"
LOCAL_PROJECTS_DIR = REPO_ROOT / "projects_local"

DEFAULT_MODEL = "claude-opus-5-5"


def get_setting(key: str, default: Any = None) -> Any:
    """Read a setting from st.secrets, falling back to the environment."""
    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # No secrets file, or running outside Streamlit (tests, scripts)
        pass
    return os.environ.get(key, default)


def model_for(task: str) -> str:
    """Model for a task: 'research' and 'burden' may use a separate override."""
    if task in ("research", "burden"):
        return get_setting("CLAUDE_MODEL_RESEARCH") or get_setting("CLAUDE_MODEL", DEFAULT_MODEL)
    return get_setting("CLAUDE_MODEL", DEFAULT_MODEL)
