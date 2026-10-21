"""DriveStore against an in-memory fake of the Drive v3 API calls it uses."""
import itertools
import re

import pytest

from core.project import Project
from core.storage_gdrive import FOLDER_MIME, DriveStore


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeFiles:
    def __init__(self):
        self.items = {}  # id -> dict(name, parents, mimeType, data)
        self.ids = (f"id{i}" for i in itertools.count())

    def _match(self, q):
        parent = re.search(r"'([^']*)' in parents", q).group(1)
        name = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
        name_value = re.sub(r"\\(.)", r"\1", name.group(1)) if name else None
        mime = re.search(r"mimeType (=|!=) '([^']*)'", q)
        out = []
        for fid, f in self.items.items():
            if parent not in f["parents"] or (name and f["name"] != name_value):
                continue
            if mime and ((f["mimeType"] == mime.group(2)) != (mime.group(1) == "=")):
                continue
            out.append({"id": fid, "name": f["name"], "size": str(len(f["data"])), "modifiedTime": "t"})
        return out

    def list(self, q, fields=None, pageToken=None, **kw):
        assert kw.get("supportsAllDrives") and kw.get("includeItemsFromAllDrives")
        return _Req(lambda: {"files": self._match(q)})

    def create(self, body, media_body=None, fields=None, **kw):
        def run():
            fid = next(self.ids)
            self.items[fid] = {"name": body["name"], "parents": body["parents"],
                               "mimeType": body.get("mimeType", "application/octet-stream"),
                               "data": media_body or b""}
            return {"id": fid, "size": str(len(media_body or b"")), "modifiedTime": "t"}
        return _Req(run)

    def update(self, fileId, media_body, fields=None, **kw):
        def run():
            self.items[fileId]["data"] = media_body
            return {"id": fileId, "modifiedTime": "t2"}
        return _Req(run)

    def get_media(self, fileId, **kw):
        return _Req(lambda: self.items[fileId]["data"])


class FakeService:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


@pytest.fixture
def store():
    svc = FakeService()
    return DriveStore(svc, "root", media_factory=lambda data, mime: data)


def test_create_list_and_round_trip(store):
    p = store.create_project(Project.new("Food labelling", owner_email="a@b.gov.au"))
    store.create_project(Project.new("Other", owner_email="c@d.gov.au"))
    folders = [f for f in store.service.files().items.values() if f["mimeType"] == FOLDER_MIME]
    assert len(folders) == 2 * 7  # project folder + 6 subfolders each
    assert [x.name for x in store.list_projects(owner_email="a@b.gov.au")] == ["Food labelling"]
    assert len(store.list_projects()) == 2
    assert store.load_project(p.id).name == "Food labelling"


def test_files_write_overwrite_read_list(store):
    p = store.create_project(Project.new("Test"))
    store.write_text(p.id, "research", "brief.md", "v1")
    store.write_text(p.id, "research", "brief.md", "v2")  # update, not duplicate
    store.write_file(p.id, "burden", "est.xlsx", b"xx")
    assert store.read_text(p.id, "research", "brief.md") == "v2"
    files = store.list_files(p.id)
    assert [(f.folder, f.name) for f in files] == [("research", "brief.md"), ("burden", "est.xlsx")]
    assert store.list_files(p.id, "research")[0].size == 2
    assert b"brief.md" in store.export_zip(p.id)


def test_rejects_bad_names_and_missing(store):
    p = store.create_project(Project.new("Test"))
    with pytest.raises(ValueError):
        store.write_text(p.id, "research", "../x.md", "no")
    with pytest.raises(ValueError):
        store.write_text(p.id, "nope", "x.md", "no")
    with pytest.raises(FileNotFoundError):
        store.load_project("missing-123")
    with pytest.raises(FileNotFoundError):
        store.read_file(p.id, "research", "absent.md")


def test_names_with_quotes_are_escaped(store):
    p = store.create_project(Project.new("Test"))
    store.write_text(p.id, "brief", "minister's brief.md", "ok")
    assert store.read_text(p.id, "brief", "minister's brief.md") == "ok"


def test_from_settings_requires_configuration(monkeypatch):
    import core.storage_gdrive as g

    monkeypatch.setattr(g, "get_setting", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="DRIVE_ROOT_FOLDER_ID"):
        DriveStore.from_settings()
