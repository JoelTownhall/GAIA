"""Project overview: framework steps, status, and folder contents."""
import streamlit as st

from core.framework import load_framework
from core.project import FOLDERS, StepStatus
from core.ui import page_footer, page_header, require_project, store

project = require_project()
fw = load_framework()

page_header(project.name, project.policy_summary or "")
if project.agency or project.decision_point:
    st.caption(" · ".join(x for x in [project.agency, project.decision_point] if x))

STATUS_LABELS = {
    StepStatus.NOT_STARTED: "Not started",
    StepStatus.IN_PROGRESS: "In progress",
    StepStatus.DONE: "Done",
    StepStatus.NOT_REQUIRED: "Not required",
}
TOOL_PAGES = {
    "research": ("views/research.py", "Research"),
    "advice": ("views/general_advice.py", "General advice"),
    "self_assessment": ("views/self_assessment.py", "Self-assessment"),
    "burden": ("views/burden_estimate.py", "Burden estimate"),
    "drafts": ("views/draft_export.py", "Draft and export"),
    "exports": ("views/draft_export.py", "Draft and export"),
}

st.subheader("Framework steps")
for step in fw.steps:
    with st.container(border=True):
        c1, c2 = st.columns([4, 1.4])
        with c1:
            st.markdown(f"**Step {step.number}: {step.title}**")
            st.write(step.summary)
            links = {TOOL_PAGES[t] for t in step.app_support if t in TOOL_PAGES}
            if links:
                cols = st.columns(len(links))
                for col, (path, label) in zip(cols, sorted(links, key=lambda x: x[1])):
                    col.page_link(path, label=label)
        with c2:
            current = project.step_status.get(step.id, StepStatus.NOT_STARTED)
            choice = st.selectbox(
                "Status",
                list(STATUS_LABELS),
                index=list(STATUS_LABELS).index(current),
                format_func=STATUS_LABELS.get,
                key=f"status-{step.id}",
            )
            if choice != current:
                project.set_step(step.id, choice)
                store().save_project(project)
                st.rerun()

st.subheader("Project folder")
files = store().list_files(project.id)
if files:
    for key, folder in FOLDERS.items():
        in_folder = [f for f in files if f.folder == key]
        if not in_folder:
            continue
        with st.expander(f"{folder}  ({len(in_folder)})"):
            for f in in_folder:
                c1, c2 = st.columns([5, 1])
                c1.write(f.name)
                c2.download_button(
                    "Download",
                    data=store().read_file(project.id, f.folder, f.name),
                    file_name=f.name,
                    key=f"dl-{f.folder}-{f.name}",
                )
else:
    st.caption("The folder is empty. Start with Research to build an evidence base.")

with st.expander("Add your own documents"):
    st.caption("Files are saved to 00_brief and used as context by the advice tools.")
    uploads = st.file_uploader("Upload", accept_multiple_files=True, label_visibility="collapsed")
    if uploads and st.button("Save to project folder"):
        for up in uploads:
            store().write_file(project.id, "brief", up.name, up.getvalue())
        project.add_log("upload", ", ".join(u.name for u in uploads))
        store().save_project(project)
        st.success(f"Saved {len(uploads)} file(s).")
        st.rerun()

st.download_button(
    "Download whole project (.zip)",
    data=store().export_zip(project.id),
    file_name=f"{project.id}.zip",
    mime="application/zip",
)

with st.expander("Activity log"):
    for entry in reversed(project.log[-50:]):
        st.caption(f"{entry.at} — {entry.action}: {entry.detail}")

page_footer()
