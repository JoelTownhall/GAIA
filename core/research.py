"""Research: Claude searches the web for evidence and writes a brief for the project folder."""
from __future__ import annotations

from datetime import datetime, timezone

from core.claude_client import build_system
from core.framework import load_framework
from core.prompts import GUARDRAILS, RESEARCH_MODE, RESEARCH_OUTPUT

FOCUS_AREAS = {
    "magnitude": "Size and trend of the problem, with Australian data where available",
    "affected": "Businesses, organisations and people affected, with counts by cohort",
    "current_policy": "Current Australian Government and state policy and regulation, and why it falls short",
    "options": "Regulatory and non-regulatory approaches used in Australia and comparable countries",
    "standards": "Relevant international standards and how other countries apply them",
    "costs": "Evidence on costs, benefits and compliance effort (time, fees, services, delays)",
    "evaluations": "Evaluations or reviews of past interventions on this problem",
}


def research_system() -> list[dict]:
    fw = load_framework()
    return build_system(GUARDRAILS, RESEARCH_MODE, RESEARCH_OUTPUT, cached_context=fw.as_prompt_text())


def research_request(problem: str, focus: list[str], questions: str = "", project_context: str = "") -> str:
    lines = ["Research the following policy problem for an Impact Analysis.", "", "Policy problem:", problem.strip()]
    if focus:
        lines += ["", "Focus on:"] + [f"- {FOCUS_AREAS[f]}" for f in focus if f in FOCUS_AREAS]
    if questions.strip():
        lines += ["", "Specific questions:", questions.strip()]
    if project_context:
        lines += ["", "Project details and documents gathered so far (use these, and don't repeat "
                  "searches for facts they already establish):", "<project>", project_context, "</project>"]
    return "\n".join(lines)


def brief_markdown(title: str, problem: str, focus: list[str], body: str, sources: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Research brief: {title}",
        "",
        f"Prepared {stamp} with IA Navigator Research (Claude with web search). Check key "
        "figures against the sources before relying on them.",
        "",
        "**Policy problem researched:** " + " ".join(problem.split()),
        "",
    ]
    if focus:
        lines += ["**Focus:** " + "; ".join(FOCUS_AREAS[f] for f in focus if f in FOCUS_AREAS), ""]
    lines += [body.strip(), "", "## Sources consulted", ""]
    if not sources:
        lines.append("No web sources were recorded.")
    for s in sources:
        marker = "" if s.get("cited") else " (consulted, not cited)"
        lines.append(f"- [{s['title']}]({s['url']}){marker}")
    return "\n".join(lines) + "\n"


def file_stem(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("research_brief_%Y%m%d-%H%M")
