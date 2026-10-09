"""Framework library: the steps and their sources."""
import streamlit as st

from core.framework import load_framework
from core.ui import page_footer, page_header

fw = load_framework()
page_header(
    "Framework library",
    f"The {fw.meta.title} sets out a five-step process. Administered by the "
    f"{fw.meta.administered_by}.",
)

if not fw.is_verified:
    st.warning(
        "Step summaries are drawn from the OIA website and have not yet been checked "
        "against the Framework and Practical Guide PDFs. Use the source links for the "
        "authoritative text."
    )

for step in fw.steps:
    src = fw.source_for(step)
    st.markdown(
        f'<div class="ian-step"><div class="num">Step {step.number}</div>'
        f'<div class="title">{step.title}</div>'
        f'<div class="summary">{step.summary}</div></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Source: [{src.title}]({step.source_url or src.url})")

st.subheader("Source documents")
for src in fw.meta.sources.values():
    st.markdown(f"- [{src.title}]({src.url})")

missing = fw.missing_source_files()
if missing:
    st.caption(
        "Not yet loaded into the app: " + ", ".join(s.title for s in missing)
        + ". Once added, the advice tools will quote and cite them directly."
    )

page_footer()
