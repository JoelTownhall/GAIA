"""Burden estimate: regulatory burden calculator following the OIA RBE Tool."""
import pandas as pd
import streamlit as st

from core.burden import (
    CATEGORY_LABELS,
    AdminItem,
    BurdenInputs,
    BurdenSuggestion,
    DelayItem,
    Settings,
    SubstantiveItem,
    calculate,
    fmt_money,
    rows_to_items,
    summary_markdown,
    to_xlsx,
)
from core.claude_client import ClaudeUnavailable, build_system, structured_reply
from core.context import build_project_context
from core.framework import load_framework
from core.prompts import BURDEN_MODE, GUARDRAILS
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
rbe = load_framework().rbe_defaults
SAVE_NAME = "burden_inputs.json"

page_header(
    "Burden estimate",
    "A first-cut estimate of the change in regulatory burden, using the method and default "
    "labour rates of the OIA Regulatory Burden Estimation Tool (July 2026). Use it to test "
    "IA threshold 1 ($20 million over 10 years) and for IA question 4.",
)

key = f"burden-{project.id}"
if key not in st.session_state:
    saved = load_json_file(project, "burden", SAVE_NAME)
    st.session_state[key] = BurdenInputs.model_validate(saved) if saved else BurdenInputs(title=project.name)
inputs: BurdenInputs = st.session_state[key]
version = st.session_state.setdefault(f"{key}-v", 0)

# --- Suggested cost items -----------------------------------------------------------
with st.expander("Suggest cost items from the project folder (optional)", expanded=not (
        inputs.administrative or inputs.substantive or inputs.delay)):
    st.caption("Claude reads the project brief and research and proposes cost items. Every number "
               "is an assumption to check with stakeholders. Suggestions replace the tables below.")
    if st.button("Suggest cost items", disabled=not claude_configured()):
        ctx = build_project_context(store(), project, folders=["brief", "research", "drafts"]).text
        with st.spinner("Working out the tasks and costs the proposal would create."):
            try:
                sug = structured_reply(
                    build_system(GUARDRAILS, BURDEN_MODE, cached_context=load_framework().as_prompt_text()),
                    [{"role": "user", "content": f"<project>\n{ctx}\n</project>\n\nSuggest cost items "
                      "for a regulatory burden estimate of this proposal."}],
                    BurdenSuggestion, task="burden", effort="high",
                )
            except ClaudeUnavailable as exc:
                st.error(str(exc))
            else:
                inputs.settings.entities = sug.entities
                inputs.administrative, inputs.substantive, inputs.delay = sug.administrative, sug.substantive, sug.delay
                inputs.assumptions = f"Entities: {sug.entities:,g} ({sug.entities_basis})\n{sug.assumptions}"
                st.session_state[f"{key}-v"] = version + 1
                st.rerun()

# --- General settings ---------------------------------------------------------------
st.subheader("General settings")
help_text = {s.id: s.guidance for s in rbe.general_settings}
c1, c2, c3, c4, c5 = st.columns(5)
s = inputs.settings
inputs.title = st.text_input("Proposal title", value=inputs.title or project.name, key=f"{key}-{version}-title")
entities = c1.number_input("Entities affected", min_value=0.0, value=float(s.entities), step=1.0, format="%.0f",
                           help=help_text["entities"] + " (required)", key=f"{key}-{version}-ent")
people = c2.number_input("People per entity", min_value=0.0, value=float(s.people_per_entity), step=1.0, format="%.0f",
                         help=help_text["people_per_entity"], key=f"{key}-{version}-ppl")
work = c3.number_input("Work-related rate ($/hr)", min_value=0.0, value=float(s.work_labour_rate),
                       help=help_text["work_labour_rate"], key=f"{key}-{version}-wr")
nonwork = c4.number_input("Non-work rate ($/hr)", min_value=0.0, value=float(s.non_work_labour_rate),
                          help=help_text["non_work_labour_rate"], key=f"{key}-{version}-nwr")
period = c5.number_input("Period (years)", min_value=1, max_value=30, value=int(s.period_years),
                         help=help_text["period_years"], key=f"{key}-{version}-per")
inputs.settings = Settings(entities=entities, people_per_entity=people, work_labour_rate=work,
                           non_work_labour_rate=nonwork, period_years=int(period))
if entities == 0:
    st.info("Enter the number of entities affected. Each cost item can also set its own count.")

# --- Cost tables ----------------------------------------------------------------------
num = st.column_config.NumberColumn
TABLES = {
    "administrative": (AdminItem, {
        "description": st.column_config.TextColumn("Description", width="large"),
        "setup_hours": num("Set-up hours (one-off)"),
        "ongoing_hours": num("Hours per occasion"),
        "frequency": num("Occasions per year"),
        "cost_type": st.column_config.SelectboxColumn("Cost type", options=["Work-related", "Non-work-related"]),
        "entities": num("Entities (if different)"),
        "people_per_entity": num("People per entity (if different)"),
        "recurring_from_year": num("Recurring from year", min_value=1, step=1),
    }),
    "substantive": (SubstantiveItem, {
        "description": st.column_config.TextColumn("Description", width="large"),
        "one_off_cost": num("One-off cost per entity ($)"),
        "recurring_cost": num("Recurring cost per entity ($)"),
        "frequency": num("Times per year"),
        "entities": num("Entities (if different)"),
        "recurring_from_year": num("Recurring from year", min_value=1, step=1),
    }),
    "delay": (DelayItem, {
        "description": st.column_config.TextColumn("Description", width="large"),
        "income_lost_per_day": num("Cost per day of delay ($)"),
        "delay_days": num("Days of delay (negative = shorter)"),
        "recurrence": num("Delays per year"),
        "one_off": st.column_config.CheckboxColumn("One-off"),
        "entities": num("Entities (if different)"),
    }),
}
INTRO = {
    "administrative": "Staff or personal time: record-keeping, reporting, training, internal processes.",
    "substantive": "Purchased services or products: audits, legal advice, software, consultants, equipment.",
    "delay": "Standby expenses and lost income while waiting on a regulatory process. The OIA asks "
             "agencies to contact it if a proposal has delay costs.",
}
for cat, (model, cols) in TABLES.items():
    st.subheader(CATEGORY_LABELS[cat])
    st.caption(INTRO[cat])
    current = getattr(inputs, cat)
    df = pd.DataFrame([i.model_dump() for i in current], columns=list(cols)) if current \
        else pd.DataFrame(columns=list(cols))
    edited = st.data_editor(df, column_config=cols, num_rows="dynamic", hide_index=True,
                            use_container_width=True, key=f"{key}-{version}-{cat}")
    try:
        setattr(inputs, cat, rows_to_items(model, edited.to_dict("records")))
    except ValueError as exc:
        st.error(f"Check the {CATEGORY_LABELS[cat].lower()} table: {exc}")

inputs.assumptions = st.text_area(
    "Assumptions and data sources", value=inputs.assumptions, height=120, key=f"{key}-{version}-assump",
    help="Record the basis for every number, as the OIA tool's Scratch Pad asks.",
)

# --- Results --------------------------------------------------------------------------
result = calculate(inputs)
st.subheader("Estimate")
m1, m2, m3 = st.columns(3)
m1.metric(f"Total over {result.period_years} years", fmt_money(result.total))
m2.metric("Average per year", fmt_money(result.annual_average))
m3.metric("IA threshold 1", "Likely met" if result.meets_threshold_1 else "Not met")
years = pd.DataFrame(
    {label: result.category_years(k) for k, label in CATEGORY_LABELS.items()},
    index=[f"Year {i}" for i in range(1, result.period_years + 1)],
)
years["Total"] = years.sum(axis=1)
st.dataframe(years.T.style.format("{:,.0f}"), use_container_width=True)
st.caption("Undiscounted. Negative figures are reductions in burden. The final estimate in the IA is "
           "the average annual change over 10 years (Practical Guide, p. 11).")

c1, c2, c3 = st.columns(3)
if c1.button("Save to project folder", type="primary"):
    save_to_project(project, "burden", SAVE_NAME, inputs.model_dump_json(indent=2), "burden_inputs")
    save_to_project(project, "burden", "burden_estimate.md", summary_markdown(inputs, result), "burden_summary")
    save_to_project(project, "burden", "burden_estimate.xlsx", to_xlsx(inputs, result), "burden_workbook")
    st.success("Saved the inputs, a summary and a workbook to 03_burden_estimate.")
c2.download_button("Download workbook (.xlsx)", to_xlsx(inputs, result), file_name="burden_estimate.xlsx")
c3.download_button("Download summary (.md)", summary_markdown(inputs, result), file_name="burden_estimate.md")

with st.expander("How the estimate is calculated"):
    for c in rbe.cost_categories:
        st.markdown(f"**{c.title}.** {c.description}".replace("$", "\\$"))
    st.markdown(f"- {rbe.initial_cost}\n- {rbe.ongoing_cost}".replace("$", "\\$"))
    st.markdown(
        "Recurring costs start in year 1 unless you set a later year, for example a yearly "
        "check that only starts after a one-off set-up. The tool's worked examples use both."
    )

page_footer(["Regulatory Burden Estimation Tool (version July 2026)"])
