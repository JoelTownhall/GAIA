"""Projects: create a project folder or open an existing one."""
import streamlit as st

from core.project import Project
from core.ui import current_user_email, page_footer, page_header, store

page_header(
    "Projects",
    "Each Impact Analysis lives in a project folder. Research, self-assessment, burden "
    "estimates and drafts are saved into it as you work, so the folder becomes the record "
    "of how the analysis was built.",
)

owner = current_user_email()
projects = store().list_projects(owner_email=owner)

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Your projects")
    if not projects:
        st.caption("No projects yet. Create one to get started.")
    for p in projects:
        with st.container(border=True):
            st.markdown(f"**{p.name}**")
            meta = " · ".join(x for x in [p.agency, f"Updated {p.updated_at[:10]}"] if x)
            st.caption(meta)
            if p.policy_summary:
                st.write(p.policy_summary[:240] + ("…" if len(p.policy_summary) > 240 else ""))
            if st.button("Open", key=f"open-{p.id}"):
                st.session_state["project_id"] = p.id
                st.switch_page("views/project_home.py")

with right:
    st.subheader("New project")
    with st.form("new_project", clear_on_submit=True):
        name = st.text_input("Project name", placeholder="e.g. Reforms to food labelling standards")
        agency = st.text_input("Agency")
        summary = st.text_area(
            "Policy problem in brief",
            help="Two or three sentences on the problem you are trying to solve. "
            "The Research tool uses this as its starting point.",
        )
        decision = st.text_input(
            "Key decision and timing",
            placeholder="e.g. Cabinet consideration, March 2027",
        )
        submitted = st.form_submit_button("Create project", type="primary")
    if submitted:
        if not name.strip():
            st.error("Enter a project name.")
        else:
            project = Project.new(
                name.strip(),
                agency=agency.strip(),
                owner_email=owner,
                policy_summary=summary.strip(),
                decision_point=decision.strip(),
            )
            store().create_project(project)
            if summary.strip():
                store().write_text(
                    project.id, "brief", "policy_problem.md",
                    f"# {project.name}\n\n## Policy problem\n\n{summary.strip()}\n",
                )
            st.session_state["project_id"] = project.id
            st.switch_page("views/project_home.py")

page_footer()
