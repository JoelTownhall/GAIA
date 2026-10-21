"""General advice: a grounded, cited chat about the user's IA."""
from datetime import datetime, timezone

import streamlit as st

from core.advice import (
    PASSAGES_PER_TURN,
    advice_system,
    build_messages,
    focus_label,
    format_passages,
    retrieval_query,
    transcript_markdown,
    user_turn_text,
)
from core.claude_client import ChatResult, ClaudeUnavailable, stream_reply
from core.context import build_project_context
from core.framework import load_framework
from core.retrieval import search
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
fw = load_framework()

page_header(
    "General advice",
    "Ask about any step of the Impact Analysis for this project. Answers draw on the 2026 "
    "Framework and Practical Guide, cite the page they rely on, and take account of the "
    "documents in your project folder.",
)

key = f"advice-{project.id}"
state = st.session_state.setdefault(key, {"api": [], "display": [], "context": None})

with st.sidebar:
    st.caption("Advice focus")
    step_no = st.selectbox(
        "Framework step", [None] + [s.number for s in fw.steps],
        format_func=lambda n: "Any step" if n is None else f"Step {n}: {fw.steps[n - 1].title}",
    )
    q_no = st.selectbox(
        "IA question", [None] + [q.number for q in fw.ia_questions],
        format_func=lambda n: "Any question" if n is None else f"Q{n}: {fw.ia_questions[n - 1].short_title}",
    )

if not claude_configured():
    claude_setup_notice()

if not state["display"]:
    st.markdown("Some starting points:")
    for example in [
        "Is my proposal in scope, and which IA thresholds might it meet?",
        "Do I need a Dashboard IA or a Detailed IA?",
        "What does IA question 3 need, and what counts as a non-regulatory option?",
        "Who signs the Statement of Sufficiency, and when?",
    ]:
        st.caption(f"- {example}")

for m in state["display"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"].replace("$", "\\$"))

question = st.chat_input("Ask about your Impact Analysis")
if question:
    focus = focus_label(step_no, q_no)
    with st.chat_message("user"):
        st.markdown(question.replace("$", "\\$"))
    if state["context"] is None:
        # Fixed for the conversation so the cached prefix stays valid.
        state["context"] = build_project_context(
            store(), project, folders=["brief", "research", "self_assessment", "burden", "drafts"]
        ).text
    results = search(retrieval_query(question, focus), k=PASSAGES_PER_TURN)
    turn = user_turn_text(question, focus, format_passages(results))
    with st.chat_message("assistant"):
        result = ChatResult()
        try:
            st.write_stream(stream_reply(
                advice_system(), build_messages(state["context"], state["api"], turn),
                task="advice", effort="medium", result=result,
            ))
        except ClaudeUnavailable as exc:
            st.error(str(exc))
        else:
            state["api"] += [{"role": "user", "content": turn},
                             {"role": "assistant", "content": result.text}]
            state["display"] += [{"role": "user", "content": question, "focus": focus},
                                 {"role": "assistant", "content": result.text}]
            if results:
                with st.expander("Passages used"):
                    for r in results:
                        p = r.passage
                        st.caption(f"{p.title}, p. {p.page} — {p.section}")

if state["display"]:
    c1, c2 = st.columns(2)
    if c1.button("Save conversation to project folder", type="primary"):
        name = datetime.now(timezone.utc).strftime("advice_notes_%Y%m%d-%H%M.md")
        save_to_project(project, "drafts", name, transcript_markdown(project.name, state["display"]),
                        "advice_saved")
        st.success(f"Saved to 04_drafts/{name}.")
    if c2.button("Start a new conversation"):
        st.session_state.pop(key, None)
        st.rerun()

page_footer(["Australian Government Impact Analysis Framework (July 2026)",
             "Impact Analysis Practical Guide for Agencies"])
