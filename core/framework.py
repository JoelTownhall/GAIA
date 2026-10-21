"""Loads the structured framework spec (content/framework_2026.yaml)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from core.config import CONTENT_DIR, REFERENCE_DIR

SPEC_PATH = CONTENT_DIR / "framework_2026.yaml"


class Source(BaseModel):
    title: str
    url: str
    local_file: str | None = None


class Citation(BaseModel):
    """Where a statement comes from: a page range in a PDF, or a sheet/cell in a workbook."""

    source: str
    section: str
    page: int | None = None
    page_end: int | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _has_locator(self) -> Citation:
        if self.page is None and not self.location:
            raise ValueError("citation needs a page or a location")
        return self

    def pages_label(self) -> str:
        if self.page is None:
            return ""
        if self.page_end and self.page_end != self.page:
            return f"pp. {self.page}-{self.page_end}"
        return f"p. {self.page}"


class Step(BaseModel):
    id: str
    number: int
    title: str
    summary: str
    source: str
    source_url: str | None = None
    app_support: list[str] = Field(default_factory=list)
    verified: bool = False
    citations: list[Citation] = Field(default_factory=list)


class ScopeItem(BaseModel):
    id: str
    title: str
    text: str
    citation: Citation


class Scope(BaseModel):
    in_scope: list[ScopeItem]
    not_required: str
    not_required_citation: Citation


class Threshold(BaseModel):
    id: str
    number: int
    title: str
    text: str
    citations: list[Citation] = Field(min_length=1)


class QuestionPrompt(BaseModel):
    text: str
    items: list[str] = Field(default_factory=list)


class IAQuestion(BaseModel):
    id: str
    number: int
    short_title: str
    question: str
    prompts: list[QuestionPrompt]
    note: str | None = None
    citation: Citation

    @field_validator("prompts", mode="before")
    @classmethod
    def _plain_prompts(cls, v: list) -> list:
        return [{"text": p} if isinstance(p, str) else p for p in v]


class SelfAssessmentCriterion(BaseModel):
    id: str
    question: int
    criterion: str
    adequate_practice: str
    best_practice: str
    citation: Citation


class SelfAssessmentScoring(BaseModel):
    ratings: list[str]
    note: str
    question_labels: dict[int, str]
    alert_below: dict[int, int]
    question_alert_text: str
    total_alert_below: int
    total_alert_text: str
    citation: Citation
    workbook_notes: list[str] = Field(default_factory=list)


class RBESetting(BaseModel):
    id: str
    label: str
    default: float | None = None
    required: bool = False
    unit: str | None = None
    guidance: str
    citation: Citation


class RBECostCategory(BaseModel):
    id: str
    title: str
    description: str
    stated_formula: str | None = None
    inputs: list[str]
    citation: Citation


class RBEOutput(BaseModel):
    label: str
    formula: str


class RBEAggregation(BaseModel):
    horizon_years: int
    discounting: str
    method: str
    outputs: list[RBEOutput]
    citation: Citation


class RBEExample(BaseModel):
    id: str
    title: str
    answer: str
    ten_year_total: float
    citation: Citation


class RBEDefaults(BaseModel):
    tool_version: str
    measurement_framework: str
    purpose: str
    purpose_citation: Citation
    general_settings: list[RBESetting]
    cost_categories: list[RBECostCategory]
    initial_cost: str
    ongoing_cost: str
    initial_ongoing_citation: Citation
    aggregation: RBEAggregation
    reporting_requirement: str
    reporting_citation: Citation
    threshold_comparison: str
    threshold_citation: Citation
    workbook_formula_notes: list[str] = Field(default_factory=list)
    worked_examples: list[RBEExample] = Field(default_factory=list)

    def setting(self, setting_id: str) -> RBESetting:
        for s in self.general_settings:
            if s.id == setting_id:
                return s
        raise KeyError(setting_id)


class SpecialCase(BaseModel):
    id: str
    title: str
    summary: str
    requirements: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(min_length=1)


class FrameworkMeta(BaseModel):
    title: str
    effective_from: str
    administered_by: str
    sources: dict[str, Source]


class Framework(BaseModel):
    meta: FrameworkMeta
    steps: list[Step]
    scope: Scope
    ia_thresholds: list[Threshold]
    ia_questions: list[IAQuestion]
    self_assessment_scoring: SelfAssessmentScoring
    self_assessment_criteria: list[SelfAssessmentCriterion]
    rbe_defaults: RBEDefaults
    special_cases: list[SpecialCase] = Field(default_factory=list)

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def source_for(self, step: Step) -> Source:
        return self.meta.sources[step.source]

    def criteria_for(self, question: int) -> list[SelfAssessmentCriterion]:
        return [c for c in self.self_assessment_criteria if c.question == question]

    def cite(self, citation: Citation) -> str:
        """Short human-readable citation, e.g. 'Impact Analysis Practical Guide ..., Step 3, p. 13'."""
        parts = [self.meta.sources[citation.source].title, citation.section]
        parts.append(citation.pages_label() or citation.location or "")
        return ", ".join(p for p in parts if p)

    def all_citations(self) -> list[Citation]:
        cits: list[Citation] = []
        for s in self.steps:
            cits += s.citations
        cits += [i.citation for i in self.scope.in_scope] + [self.scope.not_required_citation]
        for t in self.ia_thresholds:
            cits += t.citations
        cits += [q.citation for q in self.ia_questions]
        cits += [c.citation for c in self.self_assessment_criteria]
        cits.append(self.self_assessment_scoring.citation)
        rbe = self.rbe_defaults
        cits += [rbe.purpose_citation, rbe.initial_ongoing_citation, rbe.reporting_citation,
                 rbe.threshold_citation, rbe.aggregation.citation]
        cits += [s.citation for s in rbe.general_settings]
        cits += [c.citation for c in rbe.cost_categories]
        cits += [e.citation for e in rbe.worked_examples]
        for sc in self.special_cases:
            cits += sc.citations
        return cits

    @property
    def is_verified(self) -> bool:
        """True once every step has been checked against the source documents."""
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
            lines.append(f"Step {s.number}: {s.title}")
            lines.append(f"  {s.summary}")
            if s.citations:
                lines.append("  Source: " + "; ".join(self.cite(c) for c in s.citations))
            else:
                src = self.source_for(s)
                lines.append(f"  Source: {src.title} — {s.source_url or src.url}")
            if not s.verified:
                lines.append("  [Summary not yet verified against the source PDF]")
            lines.append("")
        if self.ia_thresholds:
            lines.append("IA thresholds")
            for t in self.ia_thresholds:
                lines.append(f"  IA threshold {t.number} ({t.title.lower()}): {t.text}")
            lines.append("")
        if self.ia_questions:
            lines.append(f"The 7 IA questions ({self.cite(self.ia_questions[0].citation)})")
            for q in self.ia_questions:
                lines.append(f"  Question {q.number} - {q.short_title}: {q.question}")
                for p in q.prompts:
                    lines.append(f"    - {p.text}")
                    lines += [f"      - {i}" for i in p.items]
            lines.append("")
        return "\n".join(lines).strip()


def _check_citation_sources(fw: Framework) -> None:
    unknown = {c.source for c in fw.all_citations()} - set(fw.meta.sources)
    if unknown:
        raise ValueError(f"citations refer to unknown sources: {sorted(unknown)}")


@lru_cache(maxsize=1)
def load_framework(path: Path = SPEC_PATH) -> Framework:
    with open(path, encoding="utf-8") as fh:
        fw = Framework.model_validate(yaml.safe_load(fh))
    _check_citation_sources(fw)
    return fw
