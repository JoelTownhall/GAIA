"""Self-assessment against the OIA Self-Assessment Tool, with optional suggested ratings."""
import pandas as pd
import streamlit as st

from core.claude_client import ClaudeUnavailable, build_system, structured_reply
from core.context import extract_text
from core.framework import load_framework
from core.project import FOLDERS
from core.prompts import GUARDRAILS, SELF_ASSESSMENT_MODE
from core.self_assessment import (
    RATING_LABELS,
    Assessment,
    CriterionResponse,
    Rating,
    SuggestedAssessment,
    apply_suggestions,
    criteria_prompt_text,
    filled_workbook,
    report_markdown,
    score,
)
from core.ui import (
    claude_configured,
    load_json_file,
    page_footer,
    page_header,
    require_project,
    save_to_project,
    store,
)

project = require_project()
fw = load_framework()
SAVE_NAME = "self_assessment.json"

page_header(
    "Self-assessment",
    "Rate your IA against the 26 criteria of the OIA Self-Assessment Tool (July 2026). The "
    "outcome goes to the senior official who endorses the Statement of Sufficiency "
    "(Practical Guide, p. 13). This is the agency's own assessment, not an OIA assessment.",
)

key = f"sa-{project.id}"
if key not in st.session_state:
    saved = load_json_file(project, "self_assessment", SAVE_NAME)
    st.session_state[key] = Assessment.model_validate(saved) if saved else Assessment()
assessment: Assessment = st.session_state[key]
version = st.session_state.setdefault(f"{key}-v", 0)  # bumps when suggestions replace answers

# --- Suggested ratings ------------------------------------------------------------
with st.expander("Suggest ratings from a draft IA (optional)", expanded=not assessment.responses):
    candidates = [f for f in store().list_files(project.id)
                  if f.folder in ("drafts", "exports", "brief") and f.name.lower().endswith((".md", ".docx", ".pdf", ".txt"))]
    labels = [f"{FOLDERS[f.folder]}/{f.name}" for f in candidates]
    choice = st.selectbox("Draft to assess", ["Paste text instead"] + labels)
    pasted = st.text_area("Draft IA text", height=160) if choice == "Paste text instead" else ""
    st.caption("Claude rates each criterion and says why. Review every suggestion before relying on it.")
    if st.button("Suggest ratings", disabled=not claude_configured()):
        if choice == "Paste text instead":
            doc_text, doc_name = pasted, "pasted text"
        else:
            f = candidates[labels.index(choice)]
            doc_text = extract_text(f.name, store().read_file(project.id, f.folder, f.name)) or ""
            doc_name = choice
        if not doc_text.strip():
            st.error("There is no text to assess.")
        else:
            with st.spinner("Assessing the draft against 26 criteria. This takes a minute or two."):
                try:
                    suggestion = structured_reply(
                        build_system(GUARDRAILS, SELF_ASSESSMENT_MODE, cached_context=criteria_prompt_text()),
                        [{"role": "user", "content": f"Assess this draft IA ({doc_name}).\n\n<document>\n{doc_text}\n</document>"}],
                        SuggestedAssessment, task="advice", effort="high",
                    )
                except ClaudeUnavailable as exc:
                    st.error(str(exc))
                else:
                    n = apply_suggestions(assessment, suggestion)
                    assessment.assessed_document = doc_name
                    st.session_state[f"{key}-v"] = version + 1
                    st.session_state[f"{key}-overall"] = suggestion.overall
                    st.success(f"Suggested ratings for {n} criteria. Review them below, then save.")
                    st.rerun()
    if st.session_state.get(f"{key}-overall"):
        st.info(st.session_state[f"{key}-overall"])

# --- Rating form ------------------------------------------------------------------
options = list(Rating)
for q in fw.ia_questions:
    crits = fw.criteria_for(q.number)
    done = sum(assessment.rating(c.id) != Rating.NOT_COMPLETED for c in crits)
    with st.expander(f"Question {q.number}: {q.question}  ({done} of {len(crits)} addressed)"):
        for c in crits:
            st.markdown(f"**{c.criterion}**".replace("\n", "  \n"))
            current = assessment.responses.get(c.id, CriterionResponse())
            rating = st.radio(
                "Rating", options, index=options.index(current.rating), horizontal=True,
                format_func=RATING_LABELS.get, key=f"{key}-{version}-{c.id}-r", label_visibility="collapsed",
            )
            st.caption(f"Adequate practice: {c.adequate_practice}  \nBest practice: {c.best_practice}")
            note = st.text_input("Note", value=current.note, key=f"{key}-{version}-{c.id}-n",
                                 placeholder="Evidence, or what is still needed", label_visibility="collapsed")
            assessment.responses[c.id] = CriterionResponse(rating=rating, note=note)
            st.divider()

# --- Summary ----------------------------------------------------------------------
s = score(assessment)
st.subheader("Summary")
st.dataframe(pd.DataFrame(
    [{"IA question": r.label, "Not completed": r.not_completed, "Adequate practice": r.adequate,
      "Best practice": r.best, "Alert": r.alert} for r in s.questions]
    + [{"IA question": "Totals", "Not completed": s.total_not_completed, "Adequate practice": s.total_adequate,
        "Best practice": s.total_best, "Alert": s.total_alert}]
), hide_index=True, use_container_width=True)
st.caption(fw.self_assessment_scoring.note)

c1, c2, c3 = st.columns(3)
if c1.button("Save to project folder", type="primary"):
    assessment.touch()
    save_to_project(project, "self_assessment", SAVE_NAME, assessment.model_dump_json(indent=2), "self_assessment")
    save_to_project(project, "self_assessment", "self_assessment_report.md",
                    report_markdown(assessment, project.name), "self_assessment_report")
    save_to_project(project, "self_assessment", "Impact Analysis Self-Assessment Tool (completed).xlsx",
                    filled_workbook(assessment), "self_assessment_workbook")
    st.success("Saved the ratings, a gap report and a completed copy of the OIA workbook to 02_self_assessment.")
c2.download_button("Download gap report (.md)", report_markdown(assessment, project.name),
                   file_name="self_assessment_report.md")
c3.download_button("Download completed OIA workbook", filled_workbook(assessment),
                   file_name="Impact Analysis Self-Assessment Tool (completed).xlsx")

page_footer(["Impact Analysis Self-Assessment Tool (version July 2026)"])
