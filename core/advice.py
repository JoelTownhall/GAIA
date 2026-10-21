"""General advice: grounded chat about the user's IA.

Each turn retrieves passages from the Framework and Practical Guide and sends them
with the question. The project context goes in the first user message with a cache
breakpoint, so later turns reuse it from the prompt cache.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.claude_client import build_system
from core.framework import load_framework
from core.prompts import ADVICE_CITATIONS, ADVICE_MODE, GUARDRAILS
from core.retrieval import SearchResult

SHORT_TITLES = {"framework": "Framework", "practical_guide": "Practical Guide"}
PASSAGES_PER_TURN = 6


def advice_system() -> list[dict]:
    fw = load_framework()
    return build_system(GUARDRAILS, ADVICE_MODE, ADVICE_CITATIONS, cached_context=fw.as_prompt_text())


def focus_label(step_number: int | None = None, question_number: int | None = None) -> str:
    fw = load_framework()
    parts = []
    if step_number:
        step = fw.steps[step_number - 1]
        parts.append(f"Step {step.number}: {step.title}")
    if question_number:
        q = fw.ia_questions[question_number - 1]
        parts.append(f"IA question {q.number} ({q.short_title}): {q.question}")
    return "; ".join(parts)


def retrieval_query(question: str, focus: str = "") -> str:
    return f"{question} {focus}".strip()


def format_passages(results: list[SearchResult]) -> str:
    if not results:
        return "No passages were retrieved for this question."
    lines = ["Retrieved passages:"]
    for i, r in enumerate(results, 1):
        p = r.passage
        lines.append(
            f'<passage n="{i}" source="{SHORT_TITLES.get(p.source, p.title)}" page="{p.page}" '
            f'section="{p.section}">\n{p.text}\n</passage>'
        )
    return "\n".join(lines)


def user_turn_text(question: str, focus: str, passages: str) -> str:
    parts = []
    if focus:
        parts.append(f"Current focus: {focus}")
    parts.append(passages)
    parts.append(f"My question:\n{question}")
    return "\n\n".join(parts)


def build_messages(project_context: str, history: list[dict], new_turn: str) -> list[dict]:
    """API messages: earlier turns as sent, then the new user turn.

    `history` holds {"role", "content"} pairs exactly as previously sent and received
    (append-only, so the cached prefix stays valid). The project context is attached
    to the first user turn.
    """
    turns = history + [{"role": "user", "content": new_turn}]
    messages: list[dict] = []
    for i, t in enumerate(turns):
        if i == 0 and t["role"] == "user":
            content = [
                {"type": "text", "text": f"<project>\n{project_context}\n</project>",
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": t["content"]},
            ]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": t["role"], "content": t["content"]})
    return messages


def transcript_markdown(project_name: str, display: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Advice notes: {project_name}",
        "",
        f"Saved {stamp} from IA Navigator General advice. Drafting aid only; not advice from "
        "the Office of Impact Analysis. Check requirements against the Framework and the "
        "Practical Guide.",
        "",
    ]
    for m in display:
        if m["role"] == "user":
            lines += ["## Question", ""]
            if m.get("focus"):
                lines += [f"*Focus: {m['focus']}*", ""]
        else:
            lines += ["## Advice", ""]
        lines += [m["content"].strip(), ""]
    return "\n".join(lines)
