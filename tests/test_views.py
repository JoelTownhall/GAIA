"""Page-level tests: each tool page runs with Claude replaced by a fake."""
from types import SimpleNamespace as NS

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core import claude_client
from core.config import REPO_ROOT
from core.project import Project
from core.storage import LocalStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    import core.ui

    store = LocalStore(root=tmp_path)
    monkeypatch.setattr(core.ui, "get_store", lambda: store)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    st.cache_resource.clear()
    project = store.create_project(Project.new("Food labelling", policy_summary="Labels confuse."))
    yield store, project
    st.cache_resource.clear()


def run(page, project):
    at = AppTest.from_file(str(REPO_ROOT / "views" / f"{page}.py"), default_timeout=60)
    at.session_state["project_id"] = project.id
    return at.run()


def test_general_advice_answers_and_saves(env, monkeypatch):
    store, project = env
    sent = {}

    def fake_stream(system, messages, result=None, **kw):
        sent["messages"] = messages
        result.text = "A Deputy Secretary signs it (Practical Guide, p. 13)."
        yield result.text

    monkeypatch.setattr(claude_client, "stream_reply", fake_stream)
    at = run("general_advice", project)
    at.chat_input[0].set_value("Who signs the Statement of Sufficiency?").run()
    assert not at.exception
    turn = sent["messages"][0]["content"][1]["text"]
    assert 'page="13"' in turn and "Who signs" in turn
    next(b for b in at.button if b.label == "Save conversation to project folder").click().run()
    files = [f.name for f in store.list_files(project.id, "drafts")]
    assert len(files) == 1 and files[0].startswith("advice_notes_")
    assert "Deputy Secretary" in store.read_text(project.id, "drafts", files[0])


def test_research_saves_brief_with_sources(env, monkeypatch):
    store, project = env

    def fake_web(system, messages, result=None, on_tool=None, **kw):
        on_tool("web_search")
        result.text = "## Summary\nAllergen labels are misread."
        result.content = [NS(type="web_search_tool_result", content=[NS(url="https://foodstandards.gov.au", title="FSANZ")])]
        result.stop_reason = "end_turn"
        yield result.text

    monkeypatch.setattr(claude_client, "stream_with_web_tools", fake_web)
    at = run("research", project)
    at.button[0].click().run()  # form submit
    assert not at.exception
    md = [f.name for f in store.list_files(project.id, "research") if f.name.endswith(".md")]
    assert len(md) == 1
    text = store.read_text(project.id, "research", md[0])
    assert "Allergen labels are misread." in text and "[FSANZ](https://foodstandards.gov.au)" in text


def test_self_assessment_applies_suggestions(env, monkeypatch):
    from core.self_assessment import SuggestedAssessment, SuggestedRating

    store, project = env
    store.write_text(project.id, "drafts", "draft.md", "# Draft IA\nThe problem is clear.")
    monkeypatch.setattr(claude_client, "structured_reply", lambda *a, **k: SuggestedAssessment(
        overall="Options need work.",
        ratings=[SuggestedRating(criterion_id="q1_1", rating="best", reason="Clear.", to_improve="")]))
    at = run("self_assessment", project)
    at.selectbox[0].set_value("04_drafts/draft.md").run()
    next(b for b in at.button if b.label == "Suggest ratings").click().run()
    assert not at.exception
    assert at.session_state[f"sa-{project.id}"].rating("q1_1").value == "best"
    next(b for b in at.button if b.label == "Save to project folder").click().run()
    assert "self_assessment_report.md" in [f.name for f in store.list_files(project.id, "self_assessment")]


def test_burden_suggestion_fills_tables(env, monkeypatch):
    from core.burden import AdminItem, BurdenSuggestion

    store, project = env
    monkeypatch.setattr(claude_client, "structured_reply", lambda *a, **k: BurdenSuggestion(
        entities=110, entities_basis="ABS count", assumptions="22 hours a year per business.",
        administrative=[AdminItem(description="Report", ongoing_hours=22, frequency=1)],
        substantive=[], delay=[]))
    at = run("burden_estimate", project)
    next(b for b in at.button if b.label == "Suggest cost items").click().run()
    assert not at.exception
    inputs = at.session_state[f"burden-{project.id}"]
    assert inputs.settings.entities == 110 and inputs.administrative[0].description == "Report"
    assert "ABS count" in inputs.assumptions


def test_draft_section_and_export(env, monkeypatch):
    store, project = env

    def fake_stream(system, messages, result=None, **kw):
        result.text = "Allergen labelling is inconsistent [Gap: survey data]."
        yield result.text

    monkeypatch.setattr(claude_client, "stream_reply", fake_stream)
    at = run("draft_export", project)
    next(b for b in at.button if b.label.startswith("Draft all empty sections")).click().run()
    assert not at.exception
    draft = at.session_state[f"draft-{project.id}-dashboard"]
    assert len(draft.sections) == 8 and "Gap: survey data" in draft.sections["q1"]
    assert "draft_dashboard.json" in [f.name for f in store.list_files(project.id, "drafts")]
