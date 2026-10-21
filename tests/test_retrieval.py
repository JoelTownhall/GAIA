import pytest

from core.config import REFERENCE_DIR
from core.framework import load_framework
from core.retrieval import Index, Passage, get_index, search, tokenize


def _pdfs_present() -> bool:
    fw = load_framework()
    return all((REFERENCE_DIR / fw.meta.sources[k].local_file).exists() for k in ("framework", "practical_guide"))


needs_pdfs = pytest.mark.skipif(not _pdfs_present(), reason="source PDFs not in reference_docs/oia_2026/")


def test_tokenize_drops_stopwords_and_punctuation():
    assert tokenize("What is the Statement of Sufficiency?") == ["statement", "sufficiency"]


def test_index_ranks_matching_passage_first():
    idx = Index([
        Passage("framework", "Doc", 1, "A", "status quo and non-regulatory options"),
        Passage("framework", "Doc", 2, "B", "statement of sufficiency signed by a deputy secretary"),
        Passage("framework", "Doc", 3, "C", "publication on the website"),
    ])
    results = idx.search("who signs the statement of sufficiency", k=2)
    assert results[0].passage.page == 2
    assert all(r.score > 0 for r in results)
    assert idx.search("", k=3) == []


def test_empty_index_rejected():
    with pytest.raises(ValueError):
        Index([])


@needs_pdfs
def test_index_covers_both_documents_by_page_and_section():
    idx = get_index()
    sources = {p.source for p in idx.passages}
    assert sources == {"framework", "practical_guide"}
    fw_pages = {p.page for p in idx.passages if p.source == "framework"}
    assert {9, 10, 14, 15, 16, 17, 18, 19} <= fw_pages
    sections = {p.section for p in idx.passages}
    assert "Step 3: Assess the IA > Statement of Sufficiency" in sections
    assert "Special cases > Election commitments" in sections
    # Running footers are stripped
    assert not any("Office of Impact Analysis 1" in p.text[-30:] for p in idx.passages)


@needs_pdfs
@pytest.mark.parametrize(
    "query, source, page",
    [
        ("who endorses the statement of sufficiency deputy secretary", "practical_guide", 13),
        ("election commitment alternative policy option", "framework", 19),
        ("publish within five working days", "practical_guide", 17),
        ("regulatory burden $20 million over 10 years threshold", "practical_guide", 7),
        ("What is the likely net benefit of the option", "framework", 15),
    ],
)
def test_search_finds_expected_page(query, source, page):
    results = search(query, k=3)
    assert results, query
    top = results[0].passage
    assert (top.source, top.page) == (source, page), [r.passage.citation() for r in results]
    assert top.title == load_framework().meta.sources[source].title
    assert f"p. {page}" in top.citation()


@needs_pdfs
def test_search_respects_k():
    assert len(search("impact analysis", k=4)) == 4
