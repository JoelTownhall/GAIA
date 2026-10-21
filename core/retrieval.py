"""BM25 search over the 2026 Framework and Practical Guide PDFs.

The PDFs are split into passages by page and by section heading. Headings are found
from font size: a line set noticeably larger than the document's body text starts a
new section; the largest heading size in the document marks top-level sections
(the steps). Very small lines (running headers and footers) are dropped, as are
contents pages.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from core.config import REFERENCE_DIR
from core.framework import load_framework

# Sources indexed for retrieval (keys under meta.sources in the framework spec).
PDF_SOURCES = ("framework", "practical_guide")

_HEADING_RATIO = 1.15  # line size / body size at or above which a line is a heading
_FOOTER_RATIO = 0.85  # line size / body size below which a line is a header or footer

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have if in into is it its of on or that the "
    "their there these this those to was were what when where which who will with".split()
)


@dataclass(frozen=True)
class Passage:
    source: str  # key under meta.sources
    title: str  # document title
    page: int  # printed page number (matches the PDF page index)
    section: str  # e.g. "Step 1: Preliminary analysis > 1.3. In-scope proposals ..."
    text: str

    def citation(self) -> str:
        return f"{self.title}, {self.section}, p. {self.page}"


@dataclass(frozen=True)
class SearchResult:
    passage: Passage
    score: float


def _clean(text: str) -> str:
    # Non-breaking hyphens and similar dashes are common in the OIA PDFs.
    return text.replace("‑", "-").replace("­", "").strip()


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


def _line_size(line: dict) -> float:
    return round(line["chars"][0]["size"], 1)


def chunk_pdf(path: Path, source: str, title: str) -> list[Passage]:
    """Split a PDF into passages, one per section per page."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = [(i, pg.extract_text_lines(return_chars=True)) for i, pg in enumerate(pdf.pages, 1)]

    sizes = Counter(_line_size(ln) for _, lines in pages for ln in lines if ln["chars"])
    body = sizes.most_common(1)[0][0] if sizes else 11.0
    # Top-level heading size: the largest heading size used on several pages, so a
    # one-off cover title does not count.
    pages_per_size = Counter(
        s for _, lines in pages for s in {_line_size(ln) for ln in lines if ln["chars"]}
    )
    top_size = max(
        (s for s, n in pages_per_size.items() if s >= body * _HEADING_RATIO and n >= 3),
        default=None,
    )

    passages: list[Passage] = []
    top, sub = "", ""
    for page_no, lines in pages:
        buf: list[str] = []
        last_heading_size = None

        def flush() -> None:
            text = _clean(" ".join(buf))
            if text and "....." not in text and top != "Contents":
                section = " > ".join(s for s in (top, sub) if s) or title
                passages.append(Passage(source, title, page_no, section, text))
            buf.clear()

        for ln in lines:
            if not ln["chars"]:
                continue
            size = _line_size(ln)
            text = _clean(ln["text"])
            if size < body * _FOOTER_RATIO or not text:
                continue
            if size >= body * _HEADING_RATIO:
                if last_heading_size == size:  # heading wrapped onto a second line
                    if size == top_size and not sub:
                        top = f"{top} {text}"
                    else:
                        sub = f"{sub} {text}"
                    continue
                flush()
                if size == top_size:
                    top, sub = text, ""
                else:
                    sub = text
                last_heading_size = size
                continue
            last_heading_size = None
            buf.append(text)
        flush()
    return passages


class Index:
    def __init__(self, passages: list[Passage]):
        if not passages:
            raise ValueError("no passages to index")
        self.passages = passages
        # Section headings are indexed with the body so heading words count.
        self._bm25 = BM25Okapi([tokenize(f"{p.section} {p.text}") for p in passages])

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        tokens = tokenize(query)
        if not tokens or k <= 0:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [SearchResult(self.passages[i], float(scores[i])) for i in ranked[:k] if scores[i] > 0]


def build_index(reference_dir: Path = REFERENCE_DIR) -> Index:
    fw = load_framework()
    passages: list[Passage] = []
    for key in PDF_SOURCES:
        src = fw.meta.sources[key]
        path = reference_dir / (src.local_file or "")
        if path.is_file():
            passages += chunk_pdf(path, key, src.title)
    return Index(passages)


@lru_cache(maxsize=1)
def get_index() -> Index:
    return build_index()


def search(query: str, k: int = 5) -> list[SearchResult]:
    """Top-k passages from the Framework and Practical Guide for a query."""
    return get_index().search(query, k)
