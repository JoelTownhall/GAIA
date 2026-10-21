"""Draft and export: draft the IA section by section, then export to Word."""
from datetime import datetime, timezone

import streamlit as st

from core.burden import BurdenInputs
from core.claude_client import ChatResult, ClaudeUnavailable, stream_reply
from core.context import build_project_context
from core.drafting import (
    IA_TYPE_LABELS,
    Draft,
    draft_system,
    export_docx,
    export_markdown,
    section_guidance,
    section_request,
    sections_for,
)
from core.ui import (
    claude_configured,
    claude_setup_notice,
    load_json_file,
    page_footer,
    page_header,
    require_project,
    save_to_project,
    store,
)

project = require_project()

page_header(
    "Draft and export",
    "Draft the IA one section at a time from everything in the project folder, edit it here, "
    "then export to Word. Sections follow the 7 IA questions (Framework, pp. 12-16). Move the "
    "final text into the current OIA template before submission.",
)
if not claude_configured():
    claude_setup_notice()

ia_type = st.radio("Type of IA", list(IA_TYPE_LABELS), format_func=IA_TYPE_LABELS.get, horizontal=True,
                   help="A Detailed IA is needed only if the Prime Minister or Cabinet calls one in, or the "
                        "proposal introduces a mandatory standard that deviates from an international "
                        "standard (Framework, p. 13).")
key = f"draft-{project.id}-{ia_type}"
if key not in st.session_state:
    saved = load_json_file(project, "drafts", f"draft_{ia_type}.json")
    st.session_state[key] = Draft.model_validate(saved) if saved else Draft(ia_type=ia_type, title=project.name)
draft: Draft = st.session_state[key]
version = st.session_state.setdefault(f"{key}-v", 0)
draft.title = st.text_input("Title", value=draft.title or project.name, key=f"{key}-title")

saved_burden = load_json_file(project, "burden", "burden_inputs.json")
burden = BurdenInputs.model_validate(saved_burden) if saved_burden else None
have = {f.folder for f in store().list_files(project.id)}
st.caption("Project folder: " + ", ".join(
    f"{label} {'yes' if folder in have else 'none yet'}"
    for folder, label in [("research", "research"), ("burden", "burden estimate"),
                          ("self_assessment", "self-assessment"), ("drafts", "advice notes and drafts")]))


def project_context() -> str:
    return build_project_context(
        store(), project, folders=["brief", "research", "self_assessment", "burden", "drafts"]).text


def draft_section(section, instructions: str = "") -> bool:
    result = ChatResult()
    placeholder = st.empty()
    try:
        text = placeholder.write_stream(stream_reply(
            draft_system(),
            section_request(section, ia_type, project_context(), draft.sections.get(section.id, ""), instructions),
            task="drafts", effort="high", result=result,
        ))
    except ClaudeUnavailable as exc:
        st.error(str(exc))
        return False
    draft.sections[section.id] = result.text or str(text)
    return True


sections = sections_for(ia_type)
empty = [s for s in sections if not draft.sections.get(s.id, "").strip()]
if st.button(f"Draft all empty sections ({len(empty)})", disabled=not (claude_configured() and empty)):
    for s in empty:
        with st.status(f"Drafting {s.title}", expanded=True) as status:
            ok = draft_section(s)
            status.update(state="complete" if ok else "error", expanded=False)
        if not ok:
            break
    draft.touch()
    save_to_project(project, "drafts", draft.filename(), draft.model_dump_json(indent=2), "draft_sections")
    st.session_state[f"{key}-v"] = version + 1
    st.rerun()

for s in sections:
    filled = bool(draft.sections.get(s.id, "").strip())
    label = s.title + (" (remove before publication)" if s.confidential else "") + ("" if filled else " — not drafted")
    with st.expander(label):
        st.caption(section_guidance(s).replace("\n", "  \n"))
        draft.sections[s.id] = st.text_area(
            "Text", value=draft.sections.get(s.id, ""), height=260, key=f"{key}-{version}-{s.id}",
            label_visibility="collapsed")
        words = len(draft.sections[s.id].split())
        st.caption(f"{words} words (guide: about {s.words[ia_type]})")
        instr = st.text_input("Instructions for a redraft (optional)", key=f"{key}-{version}-{s.id}-i",
                              placeholder="e.g. Shorter, and lead with the evidence on harm")
        if st.button("Redraft this section" if filled else "Draft this section", key=f"{key}-{s.id}-go",
                     disabled=not claude_configured()):
            if draft_section(s, instr):
                draft.touch()
                save_to_project(project, "drafts", draft.filename(), draft.model_dump_json(indent=2),
                                "draft_section", s.title)
                st.session_state[f"{key}-v"] = version + 1
                st.rerun()

st.subheader("Save and export")
publication = st.checkbox("Publication version (leave out sections marked for removal)",
                          help="Strategic considerations, and fiscal and revenue estimates, are removed "
                               "before publication (Practical Guide, p. 18).")
c1, c2, c3 = st.columns(3)
if c1.button("Save draft", type="primary"):
    draft.touch()
    save_to_project(project, "drafts", draft.filename(), draft.model_dump_json(indent=2), "draft_saved")
    save_to_project(project, "drafts", draft.filename().replace(".json", ".md"),
                    export_markdown(draft, project.name, project.agency, burden=burden), "draft_saved_md")
    st.success(f"Saved to 04_drafts/{draft.filename()}.")
suffix = "_publication" if publication else ""
docx_bytes = export_docx(draft, project.name, project.agency, publication=publication, burden=burden)
docx_name = f"{ia_type}_ia{suffix}.docx"
c2.download_button("Download Word document", docx_bytes, file_name=docx_name,
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
if c3.button("Save Word document to 05_exports"):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    save_to_project(project, "exports", docx_name.replace(".docx", f"_{stamp}.docx"), docx_bytes, "export")
    st.success("Saved to 05_exports.")
st.caption("Before publication, also check the document meets the Australian Government Style Manual "
           "and WCAG accessibility requirements, and provide it in a second format if it is a PDF "
           "(Practical Guide, p. 20).")

page_footer()
