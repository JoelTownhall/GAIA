"""Project model and folder layout.

A project is a folder. Each workflow stage files its outputs into a fixed
subfolder, so the folder reads as an audit trail of how the IA was built.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

FOLDERS: dict[str, str] = {
    "brief": "00_brief",
    "research": "01_research",
    "self_assessment": "02_self_assessment",
    "burden": "03_burden_estimate",
    "drafts": "04_drafts",
    "exports": "05_exports",
}

META_FILENAME = "project.json"


class StepStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    NOT_REQUIRED = "not_required"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "project"


class LogEntry(BaseModel):
    at: str = Field(default_factory=_now)
    action: str
    detail: str = ""


class Project(BaseModel):
    id: str
    name: str
    agency: str = ""
    owner_email: str = ""
    policy_summary: str = ""
    decision_point: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    # Keyed by framework step id (see content/framework_2026.yaml)
    step_status: dict[str, StepStatus] = Field(default_factory=dict)
    log: list[LogEntry] = Field(default_factory=list)

    @classmethod
    def new(cls, name: str, **kwargs) -> "Project":
        project_id = f"{slugify(name)}-{uuid.uuid4().hex[:6]}"
        project = cls(id=project_id, name=name, **kwargs)
        project.add_log("created", f"Project '{name}' created")
        return project

    def add_log(self, action: str, detail: str = "") -> None:
        self.log.append(LogEntry(action=action, detail=detail))
        self.updated_at = _now()

    def set_step(self, step_id: str, status: StepStatus) -> None:
        self.step_status[step_id] = status
        self.add_log("step_status", f"{step_id} → {status.value}")
