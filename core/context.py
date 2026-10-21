"""Project context for the AI tools: the project's details and the text of its folder.

The tools send this to Claude so advice, assessments and drafts are grounded in what
the officer has actually gathered. Anything left out (unreadable files, or text over
the size limits) is listed in the context itself, so nothing is dropped silently.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from core.project import FOLDERS, Project
from core.storage import ProjectStore

# Generous limits: Claude's context is large, but a project folder can hold big uploads.
MAX_FILE_CHARS = 120_000
MAX_TOTAL_CHARS = 400_000

TEXT_SUFFIXES = (".md", ".txt", ".csv")
# Machine-readable files each tool also writes as Markdown; the Markdown is enough.
SKIP_SUFFIXES = (".json", ".xlsx", ".zip")


@dataclass
class ProjectContext:
    text: str
    included: list[str] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)


def extract_text(name: str, data: bytes) -> str | None:
    """Plain text from a project file, or None if the type isn't supported."""
    lower = name.lower()
    if lower.endswith(TEXT_SUFFIXES):
        return data.decode("utf-8", errors="replace")
    if lower.endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n\n".join(
                f"[page {i}]\n{p.extract_text() or ''}" for i, p in enumerate(pdf.pages, 1)
            )
    if lower.endswith(".docx"):
        import docx

        doc = docx.Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts)
    return None


def project_header(project: Project) -> str:
    lines = [f"Project: {project.name}"]
    if project.agency:
        lines.append(f"Agency: {project.agency}")
    if project.decision_point:
        lines.append(f"Key decision and timing: {project.decision_point}")
    if project.policy_summary:
        lines.append(f"Policy problem in brief: {project.policy_summary}")
    if project.step_status:
        status = ", ".join(f"{k}: {v.value}" for k, v in sorted(project.step_status.items()))
        lines.append(f"Framework step status: {status}")
    return "\n".join(lines)


def build_project_context(
    store: ProjectStore,
    project: Project,
    folders: list[str] | None = None,
    max_file_chars: int = MAX_FILE_CHARS,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> ProjectContext:
    """Project details plus the readable files in the chosen folders (default: all)."""
    ctx = ProjectContext(text="")
    parts = [project_header(project)]
    total = len(parts[0])
    for f in store.list_files(project.id):
        if folders and f.folder not in folders:
            continue
        label = f"{FOLDERS[f.folder]}/{f.name}"
        if f.name.lower().endswith(SKIP_SUFFIXES):
            continue
        try:
            text = extract_text(f.name, store.read_file(project.id, f.folder, f.name))
        except Exception as exc:  # unreadable upload: say so rather than fail the tool
            ctx.omitted.append(f"{label} (could not be read: {exc.__class__.__name__})")
            continue
        if text is None:
            ctx.omitted.append(f"{label} (file type not supported)")
            continue
        text = text.strip()
        note = ""
        if len(text) > max_file_chars:
            note = f"\n[Only the first {max_file_chars:,} of {len(text):,} characters are included.]"
            text = text[:max_file_chars]
        if total + len(text) > max_total_chars:
            ctx.omitted.append(f"{label} (project context size limit reached)")
            continue
        parts.append(f'<file name="{label}">\n{text}{note}\n</file>')
        ctx.included.append(label)
        total += len(text)
    if ctx.omitted:
        parts.append("Files not included: " + "; ".join(ctx.omitted))
    ctx.text = "\n\n".join(parts)
    return ctx
