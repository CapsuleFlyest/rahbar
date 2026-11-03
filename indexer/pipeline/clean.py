"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from collections import Counter

from .models import Document, Page

RULES = [
    "Remove lines that repeat on at least 50% of pages (minimum 3 pages) after digits are "
    "normalised: running headers and footers.",
    "Remove bare page-number lines: '12', 'Page 3 of 53', '- 3 -'.",
    "Join a word hyphenated across a line break only when the line ends letter+'-' and the "
    "next line starts lowercase.",
    "Collapse runs of spaces/tabs and more than two blank lines; strip control characters.",
    "Deliberately NOT stripped: clause and list numbering ('5.4', '(a)'), headings, and "
    "Markdown table pipes, because chunking, citations and exact-term retrieval depend on them.",
]

_PAGE_NUMBER = re.compile(
    r"^\s*(?:[-–—]\s*)?(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?(?:\s*[-–—])?\s*$", re.I)
# Numbered clauses and list items are content, however often they repeat.
_CONTENT_LINE = re.compile(r"^\s*(?:\d+(?:\.\d+)+\.?\s|\(\w{1,4}\)\s)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n(?=[a-z])")


def _signature(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def _repeating_lines(pages: list[Page]) -> set[str]:
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({_signature(ln) for ln in page.text.splitlines()
                       if ln.strip() and not _CONTENT_LINE.match(ln)})
    threshold = max(3, (len(pages) + 1) // 2)
    # Markdown table rows and headings are never boilerplate, however often they repeat.
    return {sig for sig, n in counts.items()
            if n >= threshold and not sig.startswith(("|", "#"))}


def _clean_text(text: str, boilerplate: set[str]) -> str:
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = []
    for line in text.split("\n"):
        is_content = bool(_CONTENT_LINE.match(line))
        if _PAGE_NUMBER.match(line) or (line.strip() and not is_content
                                        and _signature(line) in boilerplate):
            continue
        lines.append(re.sub(r"[ \t]+", " ", line).rstrip())
    text = _HYPHEN_BREAK.sub(r"\1", "\n".join(lines))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    boilerplate = _repeating_lines(doc.pages)
    pages = [Page(source=p.source, page=p.page, text=_clean_text(p.text, boilerplate), ocr=p.ocr)
             for p in doc.pages]
    return Document(source=doc.source, doc_version=doc.doc_version,
                    superseded=doc.superseded, pages=pages)
