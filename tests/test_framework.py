from core.framework import load_framework


def test_spec_loads_with_five_ordered_steps():
    fw = load_framework()
    assert [s.number for s in fw.steps] == [1, 2, 3, 4, 5]
    assert fw.meta.effective_from == "2026-07-01"


def test_every_step_has_a_resolvable_source():
    fw = load_framework()
    for step in fw.steps:
        src = fw.source_for(step)
        assert (step.source_url or src.url).startswith("https://oia.pmc.gov.au/")


def test_prompt_text_is_deterministic_and_flags_unverified():
    fw = load_framework()
    text = fw.as_prompt_text()
    assert text == fw.as_prompt_text()
    assert "Step 3: Assess the IA" in text
    if not fw.is_verified:
        assert "not yet verified" in text


def test_no_superseded_framework_language():
    text = load_framework().as_prompt_text().lower()
    for stale in ("iala", "lord admiralty", "guide to policy impact analysis"):
        assert stale not in text
