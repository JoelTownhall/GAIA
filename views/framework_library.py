"""Framework library: steps, IA questions, self-assessment criteria, RBE defaults and sources."""
import html

import pandas as pd
import streamlit as st

from core.framework import load_framework
from core.ui import page_footer, page_header

fw = load_framework()


def md(text: str) -> str:
    """Escape dollar signs so Streamlit does not render them as LaTeX."""
    return text.replace("$", "\\$")


def cites(citations) -> str:
    return "Source: " + "; ".join(fw.cite(c) for c in citations)


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

tab_steps, tab_questions, tab_sa, tab_rbe, tab_cases, tab_search = st.tabs(
    ["Steps", "IA questions", "Self-assessment criteria", "Regulatory burden defaults",
     "Thresholds and special cases", "Search the documents"]
)

with tab_steps:
    for step in fw.steps:
        st.markdown(
            f'<div class="ian-step"><div class="num">Step {step.number}</div>'
            f'<div class="title">{html.escape(step.title)}</div>'
            f'<div class="summary">{md(html.escape(step.summary))}</div></div>',
            unsafe_allow_html=True,
        )
        st.caption(md(cites(step.citations)))

with tab_questions:
    st.markdown(
        "The 7 IA questions need to be considered in all IAs. Wording is as in the Framework."
    )
    for q in fw.ia_questions:
        with st.expander(f"Question {q.number} – {q.short_title}: {q.question}", expanded=q.number == 1):
            lines = []
            for p in q.prompts:
                lines.append(f"- {md(p.text)}")
                lines += [f"    - {md(i)}" for i in p.items]
            st.markdown("\n".join(lines))
            if q.note:
                st.markdown(md(q.note))
            st.caption(md(cites([q.citation])))

with tab_sa:
    scoring = fw.self_assessment_scoring
    st.markdown(
        f"Each criterion is rated **{'**, **'.join(scoring.ratings)}**. "
        f"{md(scoring.note)}"
    )
    st.caption(md(cites([scoring.citation])))
    for q in fw.ia_questions:
        crits = fw.criteria_for(q.number)
        with st.expander(f"Question {q.number}: {q.question} ({len(crits)} criteria)"):
            for c in crits:
                st.markdown(f"**{md(c.criterion)}**".replace("\n", "  \n"))
                st.markdown(
                    f"- *Adequate practice:* {md(c.adequate_practice)}\n"
                    f"- *Best practice:* {md(c.best_practice)}"
                )
                st.caption(md(cites([c.citation])))
    if scoring.workbook_notes:
        with st.expander("Notes on the workbook"):
            st.markdown("\n".join(f"- {md(n)}" for n in scoring.workbook_notes))

with tab_rbe:
    rbe = fw.rbe_defaults
    st.markdown(md(rbe.purpose))
    st.caption(md(cites([rbe.purpose_citation])))

    st.subheader("General settings")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Setting": s.label,
                    "Default": "Required (no default)" if s.required else f"{s.default:g}",
                    "Guidance": s.guidance,
                    "Source": s.citation.location,
                }
                for s in rbe.general_settings
            ]
        ).astype(str),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Cost categories")
    for c in rbe.cost_categories:
        text = f"**{c.title}.** {md(c.description)}"
        if c.stated_formula:
            text += f" Calculated as: {md(c.stated_formula)}"
        st.markdown(text)
        st.caption(md(cites([c.citation])))
    st.markdown(f"- {md(rbe.initial_cost)}\n- {md(rbe.ongoing_cost)}")
    st.caption(md(cites([rbe.initial_ongoing_citation])))

    st.subheader("Horizon and averaging")
    st.markdown(md(rbe.aggregation.method))
    st.markdown("\n".join(f"- {md(o.label)}" for o in rbe.aggregation.outputs))
    st.caption(md(cites([rbe.aggregation.citation])))
    st.markdown(md(rbe.reporting_requirement))
    st.caption(md(cites([rbe.reporting_citation])))
    st.markdown(md(rbe.threshold_comparison))
    st.caption(md(cites([rbe.threshold_citation])))

    if rbe.workbook_formula_notes:
        with st.expander("Where the workbook formulas differ from its instructions"):
            st.markdown("\n".join(f"- {md(n)}" for n in rbe.workbook_formula_notes))

    with st.expander("Worked examples from the tool"):
        for ex in rbe.worked_examples:
            st.markdown(f"- **{md(ex.title)}**: {md(ex.answer)}")

with tab_cases:
    st.subheader("Scope")
    for item in fw.scope.in_scope:
        st.markdown(f"**{item.title}:** {md(item.text)}")
        st.caption(md(cites([item.citation])))
    st.markdown(md(fw.scope.not_required))
    st.caption(md(cites([fw.scope.not_required_citation])))

    st.subheader("IA thresholds")
    st.markdown(
        "An in-scope proposal that is expected to meet or exceed one or more thresholds "
        "requires an IA."
    )
    for t in fw.ia_thresholds:
        st.markdown(f"**IA threshold {t.number} ({t.title.lower()}):** {md(t.text)}")
        st.caption(md(cites(t.citations)))

    st.subheader("Special cases")
    for sc in fw.special_cases:
        with st.expander(sc.title):
            st.markdown(md(sc.summary))
            if sc.requirements:
                st.markdown("\n".join(f"- {md(r)}" for r in sc.requirements))
            st.caption(md(cites(sc.citations)))

with tab_search:
    query = st.text_input(
        "Search the Framework and Practical Guide",
        placeholder="For example: who signs the Statement of Sufficiency",
    )
    if query:
        from core.retrieval import search

        results = search(query, k=5)
        if not results:
            st.info("No matching passages.")
        for r in results:
            p = r.passage
            st.markdown(f"**{html.escape(p.title)}**, p. {p.page} — {html.escape(p.section)}")
            st.markdown(f"> {md(p.text)}")

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
