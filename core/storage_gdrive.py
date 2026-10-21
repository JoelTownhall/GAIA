"""Google Drive project storage.

Each project is a Drive folder (named by project id) under DRIVE_ROOT_FOLDER_ID,
holding project.json and the standard subfolders. The app authenticates as a Google
Cloud service account; share the root folder (or the shared drive) with the service
account's email as an Editor.

Settings (Streamlit secrets):
    STORAGE_BACKEND = "gdrive"
    DRIVE_ROOT_FOLDER_ID = "<folder id>"
    [gcp_service_account]  ... service account key fields ...
"""
from __future__ import annotations

import io

from core.config import get_setting
from core.project import FOLDERS, META_FILENAME, Project
from core.storage import ProjectStore, StoredFile, _check_folder, _check_name

FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive"]
_COMMON = {"supportsAllDrives": True}
_LIST = {"supportsAllDrives": True, "includeItemsFromAllDrives": True, "pageSize": 1000}


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _media(data: bytes, mimetype: str = "application/octet-stream"):
    from googleapiclient.http import MediaIoBaseUpload

    return MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)


class DriveStore(ProjectStore):
    def __init__(self, service, root_folder_id: str, media_factory=_media):
        self.service = service
        self.root = root_folder_id
        self._media = media_factory
        self._folder_cache: dict[tuple[str, str], str] = {}

    @classmethod
    def from_settings(cls) -> "DriveStore":
        root = get_setting("DRIVE_ROOT_FOLDER_ID")
        info = get_setting("gcp_service_account")
        if not root or not info:
            raise RuntimeError(
                "Google Drive storage needs DRIVE_ROOT_FOLDER_ID and [gcp_service_account] in the "
                "app's secrets. See README, 'Google Drive storage'."
            )
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(dict(info), scopes=SCOPES)
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return cls(service, root)

    # --- Drive helpers ---------------------------------------------------------------

    def _find(self, parent: str, name: str, folder: bool | None = None) -> dict | None:
        q = f"'{_q(parent)}' in parents and name = '{_q(name)}' and trashed = false"
        if folder is True:
            q += f" and mimeType = '{FOLDER_MIME}'"
        elif folder is False:
            q += f" and mimeType != '{FOLDER_MIME}'"
        res = self.service.files().list(q=q, fields="files(id,name,size,modifiedTime,mimeType)", **_LIST).execute()
        files = res.get("files", [])
        return files[0] if files else None

    def _children(self, parent: str, folder: bool) -> list[dict]:
        op = "=" if folder else "!="
        q = f"'{_q(parent)}' in parents and mimeType {op} '{FOLDER_MIME}' and trashed = false"
        out, token = [], None
        while True:
            res = self.service.files().list(
                q=q, fields="nextPageToken,files(id,name,size,modifiedTime)", pageToken=token, **_LIST
            ).execute()
            out += res.get("files", [])
            token = res.get("nextPageToken")
            if not token:
                return out

    def _folder(self, parent: str, name: str, create: bool = False) -> str | None:
        key = (parent, name)
        if key in self._folder_cache:
            return self._folder_cache[key]
        found = self._find(parent, name, folder=True)
        if found is None:
            if not create:
                return None
            found = self.service.files().create(
                body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}, fields="id", **_COMMON
            ).execute()
        self._folder_cache[key] = found["id"]
        return found["id"]

    def _project_folder(self, project_id: str, create: bool = False) -> str:
        fid = self._folder(self.root, _check_name(project_id), create=create)
        if fid is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        return fid

    def _put(self, parent: str, name: str, data: bytes, mimetype: str) -> dict:
        existing = self._find(parent, name, folder=False)
        media = self._media(data, mimetype)
        if existing:
            return self.service.files().update(
                fileId=existing["id"], media_body=media, fields="id,size,modifiedTime", **_COMMON
            ).execute()
        return self.service.files().create(
            body={"name": name, "parents": [parent]}, media_body=media,
            fields="id,size,modifiedTime", **_COMMON,
        ).execute()

    def _get(self, parent: str, name: str) -> bytes:
        found = self._find(parent, name, folder=False)
        if found is None:
            raise FileNotFoundError(name)
        return self.service.files().get_media(fileId=found["id"], **_COMMON).execute()

    # --- ProjectStore ----------------------------------------------------------------

    def list_projects(self, owner_email: str = "") -> list[Project]:
        projects = []
        for folder in self._children(self.root, folder=True):
            self._folder_cache[(self.root, folder["name"])] = folder["id"]
            try:
                project = Project.model_validate_json(self._get(folder["id"], META_FILENAME))
            except (FileNotFoundError, ValueError):
                continue  # not a project folder
            if not owner_email or project.owner_email == owner_email:
                projects.append(project)
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def create_project(self, project: Project) -> Project:
        pid = self._project_folder(project.id, create=True)
        for sub in FOLDERS.values():
            self._folder(pid, sub, create=True)
        self.save_project(project)
        return project

    def load_project(self, project_id: str) -> Project:
        return Project.model_validate_json(self._get(self._project_folder(project_id), META_FILENAME))

    def save_project(self, project: Project) -> None:
        data = project.model_dump_json(indent=2).encode("utf-8")
        self._put(self._project_folder(project.id, create=True), META_FILENAME, data, "application/json")

    def write_file(self, project_id: str, folder: str, name: str, data: bytes) -> StoredFile:
        sub = self._folder(self._project_folder(project_id), _check_folder(folder), create=True)
        res = self._put(sub, _check_name(name), data, _mimetype(name))
        return StoredFile(folder=folder, name=name, size=len(data), modified=res.get("modifiedTime", ""))

    def read_file(self, project_id: str, folder: str, name: str) -> bytes:
        sub = self._folder(self._project_folder(project_id), _check_folder(folder))
        if sub is None:
            raise FileNotFoundError(name)
        return self._get(sub, _check_name(name))

    def list_files(self, project_id: str, folder: str | None = None) -> list[StoredFile]:
        pid = self._project_folder(project_id)
        files = []
        for key in [folder] if folder else list(FOLDERS):
            sub = self._folder(pid, _check_folder(key))
            if sub is None:
                continue
            for f in sorted(self._children(sub, folder=False), key=lambda f: f["name"]):
                files.append(StoredFile(folder=key, name=f["name"], size=int(f.get("size", 0)),
                                        modified=f.get("modifiedTime", "")))
        return files


def _mimetype(name: str) -> str:
    lower = name.lower()
    for ext, mime in {
        ".md": "text/markdown", ".txt": "text/plain", ".json": "application/json",
        ".csv": "text/csv", ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.items():
        if lower.endswith(ext):
            return mime
    return "application/octet-stream"


def describe_service_account() -> str:
    """Email of the configured service account, for setup instructions in the UI."""
    info = get_setting("gcp_service_account")
    try:
        return dict(info).get("client_email", "") if info else ""
    except (TypeError, ValueError):
        return ""
