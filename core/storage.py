"""Project storage.

`ProjectStore` is the interface every backend implements. `LocalStore` keeps
projects on local disk (development, tests, and the fallback when Google Drive
isn't configured). The Google Drive backend lives in `storage_gdrive.py`.
"""
from __future__ import annotations

import io
import json
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from core.config import LOCAL_PROJECTS_DIR, get_setting
from core.project import FOLDERS, META_FILENAME, Project


@dataclass(frozen=True)
class StoredFile:
    folder: str  # key in FOLDERS, e.g. "research"
    name: str
    size: int
    modified: str = ""


class ProjectStore(ABC):
    """Backend-agnostic project folder operations."""

    @abstractmethod
    def list_projects(self, owner_email: str = "") -> list[Project]: ...

    @abstractmethod
    def create_project(self, project: Project) -> Project: ...

    @abstractmethod
    def load_project(self, project_id: str) -> Project: ...

    @abstractmethod
    def save_project(self, project: Project) -> None: ...

    @abstractmethod
    def write_file(self, project_id: str, folder: str, name: str, data: bytes) -> StoredFile: ...

    @abstractmethod
    def read_file(self, project_id: str, folder: str, name: str) -> bytes: ...

    @abstractmethod
    def list_files(self, project_id: str, folder: str | None = None) -> list[StoredFile]: ...

    def write_text(self, project_id: str, folder: str, name: str, text: str) -> StoredFile:
        return self.write_file(project_id, folder, name, text.encode("utf-8"))

    def read_text(self, project_id: str, folder: str, name: str) -> str:
        return self.read_file(project_id, folder, name).decode("utf-8")

    def export_zip(self, project_id: str) -> bytes:
        """The whole project folder as a zip, laid out exactly as stored."""
        project = self.load_project(project_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{project.id}/{META_FILENAME}", project.model_dump_json(indent=2))
            for f in self.list_files(project_id):
                data = self.read_file(project_id, f.folder, f.name)
                zf.writestr(f"{project.id}/{FOLDERS[f.folder]}/{f.name}", data)
        return buf.getvalue()


def _check_folder(folder: str) -> str:
    if folder not in FOLDERS:
        raise ValueError(f"Unknown project folder: {folder!r}")
    return FOLDERS[folder]


def _check_name(name: str) -> str:
    # File names come from users and from model output, so keep them flat.
    if not name or "/" in name or "\\" in name or name in (".", "..") or name.startswith("."):
        raise ValueError(f"Invalid file name: {name!r}")
    return name


class LocalStore(ProjectStore):
    def __init__(self, root: Path = LOCAL_PROJECTS_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        path = (self.root / _check_name(project_id)).resolve()
        if path.parent != self.root.resolve():
            raise ValueError(f"Invalid project id: {project_id!r}")
        return path

    def list_projects(self, owner_email: str = "") -> list[Project]:
        projects = []
        for meta in sorted(self.root.glob(f"*/{META_FILENAME}")):
            project = Project.model_validate_json(meta.read_text())
            if not owner_email or project.owner_email == owner_email:
                projects.append(project)
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def create_project(self, project: Project) -> Project:
        pdir = self._project_dir(project.id)
        for sub in FOLDERS.values():
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        self.save_project(project)
        return project

    def load_project(self, project_id: str) -> Project:
        meta = self._project_dir(project_id) / META_FILENAME
        return Project.model_validate_json(meta.read_text())

    def save_project(self, project: Project) -> None:
        meta = self._project_dir(project.id) / META_FILENAME
        meta.write_text(project.model_dump_json(indent=2))

    def write_file(self, project_id: str, folder: str, name: str, data: bytes) -> StoredFile:
        path = self._project_dir(project_id) / _check_folder(folder) / _check_name(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredFile(folder=folder, name=name, size=len(data))

    def read_file(self, project_id: str, folder: str, name: str) -> bytes:
        return (self._project_dir(project_id) / _check_folder(folder) / _check_name(name)).read_bytes()

    def list_files(self, project_id: str, folder: str | None = None) -> list[StoredFile]:
        pdir = self._project_dir(project_id)
        keys = [folder] if folder else list(FOLDERS)
        files = []
        for key in keys:
            sub = pdir / _check_folder(key)
            if not sub.exists():
                continue
            for p in sorted(sub.iterdir()):
                if p.is_file():
                    stat = p.stat()
                    files.append(StoredFile(folder=key, name=p.name, size=stat.st_size))
        return files


def get_store() -> ProjectStore:
    """The configured backend. Google Drive when STORAGE_BACKEND=gdrive."""
    if str(get_setting("STORAGE_BACKEND", "local")).lower() == "gdrive":
        from core.storage_gdrive import DriveStore

        return DriveStore.from_settings()
    return LocalStore()


def serialise_json(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
