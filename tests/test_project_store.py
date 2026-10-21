import io
import zipfile

import pytest

from core.project import Project, StepStatus, slugify
from core.storage import LocalStore


@pytest.fixture
def store(tmp_path):
    return LocalStore(root=tmp_path)


def test_slugify():
    assert slugify("Reforms to Food Labelling!") == "reforms-to-food-labelling"
    assert slugify("!!!") == "project"


def test_create_and_round_trip(store):
    p = store.create_project(Project.new("Food labelling", agency="DHDA", owner_email="a@b.gov.au"))
    p.set_step("step1", StepStatus.IN_PROGRESS)
    store.save_project(p)

    loaded = store.load_project(p.id)
    assert loaded.name == "Food labelling"
    assert loaded.step_status["step1"] == StepStatus.IN_PROGRESS
    assert [e.action for e in loaded.log] == ["created", "step_status"]


def test_list_filters_by_owner(store):
    store.create_project(Project.new("A", owner_email="a@x"))
    store.create_project(Project.new("B", owner_email="b@x"))
    assert [p.name for p in store.list_projects("a@x")] == ["A"]
    assert len(store.list_projects()) == 2


def test_files_and_zip(store):
    p = store.create_project(Project.new("Zip me"))
    store.write_text(p.id, "research", "brief.md", "# Brief")
    store.write_file(p.id, "burden", "rbe.xlsx", b"\x00\x01")

    assert store.read_text(p.id, "research", "brief.md") == "# Brief"
    assert {(f.folder, f.name) for f in store.list_files(p.id)} == {
        ("research", "brief.md"),
        ("burden", "rbe.xlsx"),
    }

    names = zipfile.ZipFile(io.BytesIO(store.export_zip(p.id))).namelist()
    assert f"{p.id}/project.json" in names
    assert f"{p.id}/01_research/brief.md" in names
    assert f"{p.id}/03_burden_estimate/rbe.xlsx" in names


@pytest.mark.parametrize("bad", ["../x", "a/b", ".hidden", "", ".."])
def test_rejects_unsafe_file_names(store, bad):
    p = store.create_project(Project.new("Safe"))
    with pytest.raises(ValueError):
        store.write_text(p.id, "brief", bad, "x")


def test_rejects_unknown_folder(store):
    p = store.create_project(Project.new("Folders"))
    with pytest.raises(ValueError):
        store.write_text(p.id, "nope", "a.md", "x")


def test_rejects_project_id_traversal(store):
    with pytest.raises(ValueError):
        store.load_project("../etc")


def test_email_domain_allowlist():
    from core.ui import email_allowed

    assert email_allowed("a@pmc.gov.au", "")
    assert email_allowed("a@pmc.gov.au", "gov.au")
    assert email_allowed("a@health.gov.au", "pmc.gov.au, health.gov.au")
    assert not email_allowed("a@gmail.com", "gov.au")
    assert not email_allowed("a@notgov.au", "gov.au")
    assert not email_allowed("", "gov.au")
