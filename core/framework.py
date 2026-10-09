"""Loads the structured framework spec (content/framework_2026.yaml)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from core.config import CONTENT_DIR, REFERENCE_DIR

SPEC_PATH = CONTENT_DIR / "framework_2026.yaml"


class Source(BaseModel):
    title: str
    url: str
    local_file: str | None = None


class Step(BaseModel):
    id: str
    number: int
    title: str
    summary: str
    source: str
    source_url: str | None = None
    app_support: list[str] = Field(default_factory=list)
    verified: bool = False


class FrameworkMeta(BaseModel):
    title: str
    effective_from: str
    administered_by: str
    sources: dict[str, Source]


class Framework(BaseModel):
    meta: FrameworkMeta
    steps: list[Step]
    ia_questions: list[dict] = Field(default_factory=list)
    self_assessment_criteria: list[dict] = Field(default_factory=list)
    rbe_defaults: dict = Field(default_factory=dict)
    special_cases: list[dict] = Field(default_factory=list)

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def source_for(self, step: Step) -> Source:
        return self.meta.sources[step.source]

    @property
    def is_verified(self) -> bool:
        """True once every step has been checked against the source PDFs."""
        return all(s.verified for s in self.steps)

    def missing_source_files(self, reference_dir: Path = REFERENCE_DIR) -> list[Source]:
        return [
            src
            for src in self.meta.sources.values()
            if src.local_file and not (reference_dir / src.local_file).exists()
        ]

    def as_prompt_text(self) -> str:
        """Deterministic plain-text rendering for the system prompt (cache-stable)."""
        lines = [f"{self.meta.title} (effective {self.meta.effective_from})", ""]
        for s in self.steps:
            src = self.source_for(s)
            lines.append(f"Step {s.number}: {s.title}")
            lines.append(f"  {s.summary}")
            lines.append(f"  Source: {src.title} — {s.source_url or src.url}")
            if not s.verified:
                lines.append("  [Summary not yet verified against the source PDF]")
            lines.append("")
        return "\n".join(lines).strip()


@lru_cache(maxsize=1)
def load_framework(path: Path = SPEC_PATH) -> Framework:
    with open(path, encoding="utf-8") as fh:
        return Framework.model_validate(yaml.safe_load(fh))
