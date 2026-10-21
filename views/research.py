"""Research: Claude searches the web for evidence and files a research brief."""
import json

import streamlit as st

from core.claude_client import ChatResult, ClaudeUnavailable, collect_sources, stream_with_web_tools
from core.context import build_project_context
from core.research import FOCUS_AREAS, brief_markdown, file_stem, research_request, research_system
from core.ui import (
    claude_configured,
    claude_setup_notice,
    page_footer,
    page_header,
    require_project,
    save_to_project,
    store,
)

project = require_project()

page_header(
    "Research",
    "Build the evidence base for IA questions 1 to 5. Claude searches the web, prefers "
    "Australian government and official sources, and writes a research brief with a full "
    "source list. The brief is saved to 01_research and used by the other tools.",
)

if not claude_configured():
    claude_setup_notice()

with st.form("research"):
    problem = st.text_area("Policy problem", value=project.policy_summary, height=120,
                           help="What is the problem, who does it affect, and why might government act?")
    focus = st.multiselect(
        "Focus areas", list(FOCUS_AREAS), default=["magnitude", "affected", "current_policy", "options", "costs"],
        format_func=FOCUS_AREAS.get,
    )
    questions = st.text_area("Specific questions (optional)", height=80,
                             placeholder="e.g. How many food businesses would need to relabel products?")
    use_folder = st.checkbox("Give Claude the documents already in the project folder", value=True)
    go = st.form_submit_button("Run research", type="primary", disabled=not claude_configured())

if go:
    if not problem.strip():
        st.error("Describe the policy problem first.")
        st.stop()
    context = ""
    if use_folder:
        context = build_project_context(store(), project, folders=["brief", "research"]).text
    status = st.status("Researching. This usually takes a few minutes.", expanded=True)
    counts = {"web_search": 0, "web_fetch": 0}

    def on_tool(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1
        status.update(label=f"Researching: {counts['web_search']} searches, {counts['web_fetch']} pages read")

    result = ChatResult()
    with status:
        try:
            body = st.write_stream(stream_with_web_tools(
                research_system(),
                [{"role": "user", "content": research_request(problem, focus, questions, context)}],
                task="research", effort="high", result=result, on_tool=on_tool,
            ))
        except ClaudeUnavailable as exc:
            status.update(label="Research stopped", state="error")
            st.error(str(exc))
            st.stop()
    status.update(label="Research complete", state="complete", expanded=False)
    sources = collect_sources(result.content)
    stem = file_stem()
    brief = brief_markdown(project.name, problem, focus, result.text or str(body), sources)
    save_to_project(project, "research", f"{stem}.md", brief, "research_brief")
    store().write_text(project.id, "research", f"{stem}_sources.json", json.dumps(sources, indent=2))
    if result.stop_reason == "max_tokens":
        st.warning("The brief reached the length limit and may be cut short. Narrow the focus and run again.")
    st.success(f"Saved to 01_research/{stem}.md with {len(sources)} sources.")
    st.session_state[f"research-last-{project.id}"] = f"{stem}.md"

st.subheader("Research briefs in this project")
briefs = [f for f in store().list_files(project.id, "research") if f.name.endswith(".md")]
if not briefs:
    st.caption("None yet.")
for f in reversed(briefs):
    with st.expander(f.name, expanded=f.name == st.session_state.get(f"research-last-{project.id}")):
        text = store().read_text(project.id, "research", f.name)
        st.markdown(text.replace("$", "\\$"))
        st.download_button("Download", text, file_name=f.name, key=f"dl-{f.name}")

page_footer()
