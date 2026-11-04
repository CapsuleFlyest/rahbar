"""Stage 3: Chunk. Structure-aware, with overlap.

Unit: size and overlap are counted in *words* (whitespace-separated tokens), not model
tokens: cheap, deterministic and close enough for a 400-word budget.

Structure-aware strategy (default): sections, then paragraphs, then sentences, then words,
always keeping a chunk at or under `size` words. Every chunk starts with its section
heading line, so the embedding sees what the passage is about. Tables are atomic: a table
that does not fit is split by rows, repeating its header row. Overlap (the last `overlap`
words of the previous chunk) is carried only inside one section, never across a heading,
and never into or out of a table.

Fixed strategy (CHUNK_STRATEGY=fixed): plain windows of `size` words, used for the
break-one-stage experiment in docs/FAILURE-ANALYSIS.md.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .models import Chunk, Document

_MD_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_KEYWORD_HEADING = re.compile(r"^(chapter|section|article|part|annex|appendix)\s+[\dIVXivx]+\b",
                              re.I)
_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)+|\d+\.)\s+[A-Za-z]")
_CLAUSE_START = re.compile(r"^(?:\d+(?:\.\d+)+\.?\s|\(\w{1,4}\)\s|[•●▪*-]\s)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def count_tokens(text: str) -> int:
    return len(text.split())


def heading_label(line: str) -> str | None:
    """Return the heading text when `line` looks like a section heading, else None."""
    stripped = line.strip()
    if not stripped or stripped.startswith("|"):
        return None
    md = _MD_HEADING.match(stripped)
    if md:
        return md.group(1).strip()
    words = stripped.split()
    if len(words) > 12 or stripped.endswith((".", ",", ";", ":")):
        return None
    if _KEYWORD_HEADING.match(stripped) or _NUMBERED_HEADING.match(stripped):
        return stripped
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 3 and stripped.isupper() and len(words) <= 10:
        return stripped
    return None


@dataclass
class _Section:
    label: str
    paragraphs: list[tuple[str, str, int]] = field(default_factory=list)  # (kind, text, page)


def _parse_sections(doc: Document) -> list[_Section]:
    sections = [_Section("Preamble")]
    para: list[str] = []
    table: list[str] = []
    para_page = 1

    def flush_para() -> None:
        if para:
            sections[-1].paragraphs.append(("text", " ".join(para), para_page))
            para.clear()

    def flush_table() -> None:
        if table:
            sections[-1].paragraphs.append(("table", "\n".join(table), para_page))
            table.clear()

    for page in doc.pages:
        for raw in page.text.split("\n"):
            line = raw.strip()
            if not line:
                flush_para()
                flush_table()
                continue
            if line.startswith("|"):
                flush_para()
                if not table:
                    para_page = page.page
                table.append(line)
                continue
            flush_table()
            label = heading_label(line)
            if label is not None:
                flush_para()
                sections.append(_Section(label))
                continue
            if para and _CLAUSE_START.match(line):
                flush_para()
            if not para:
                para_page = page.page
            para.append(line)
    flush_para()
    flush_table()
    return [s for s in sections if s.paragraphs]


def _split_words(text: str, limit: int) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + limit]) for i in range(0, len(words), limit)]


def _split_text(text: str, limit: int) -> list[str]:
    """Paragraph -> sentences -> words, every piece at most `limit` words."""
    if count_tokens(text) <= limit:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    current_n = 0
    for sentence in _SENTENCE_END.split(text):
        n = count_tokens(sentence)
        if n > limit:
            if current:
                pieces.append(" ".join(current))
                current, current_n = [], 0
            pieces.extend(_split_words(sentence, limit))
            continue
        if current_n + n > limit and current:
            pieces.append(" ".join(current))
            current, current_n = [], 0
        current.append(sentence)
        current_n += n
    if current:
        pieces.append(" ".join(current))
    return pieces


def _split_table(text: str, limit: int) -> list[str]:
    if count_tokens(text) <= limit:
        return [text]
    lines = text.split("\n")
    header = lines[:2] if len(lines) > 2 and set(lines[1].replace("|", "").strip()) <= set("- :") \
        else lines[:1]
    header_n = count_tokens("\n".join(header))
    pieces: list[str] = []
    current: list[str] = []
    current_n = header_n
    for row in lines[len(header):]:
        n = count_tokens(row)
        if current and current_n + n > limit:
            pieces.append("\n".join(header + current))
            current, current_n = [], header_n
        current.append(row)
        current_n += n
    if current:
        pieces.append("\n".join(header + current))
    return pieces


def _slug(source: str) -> str:
    stem = source.rsplit(".", 1)[0] if "." in source else source
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "doc"


def _make_chunk(doc: Document, ordinal: int, section: str, page: int, text: str) -> Chunk:
    return Chunk(id=f"{_slug(doc.source)}-{ordinal:04d}", text=text, source=doc.source,
                 section=section, page=page, doc_version=doc.doc_version,
                 superseded=doc.superseded)


def _chunk_structured(doc: Document, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _parse_sections(doc):
        heading_n = count_tokens(section.label)
        budget = size - heading_n if size - heading_n >= max(size // 2, 1) else max(size // 2, 1)
        # (kind, text, page) pieces, each already within the budget
        pieces: list[tuple[str, str, int]] = []
        # Leave room for the overlap words carried in from the previous chunk: a prose piece
        # that fills the whole budget would leave no space for them (overlap would be 0).
        prose_limit = max(budget - overlap, budget // 2) if overlap > 0 else budget
        for kind, text, page in section.paragraphs:
            split = (_split_table(text, budget) if kind == "table"
                     else _split_text(text, prose_limit))
            pieces.extend((kind, p, page) for p in split)

        body: list[str] = []
        body_n = 0
        first_page = pieces[0][2]
        last_kind = ""
        tail_words: list[str] = []   # prose words of the previous chunk, for overlap

        def emit() -> None:
            nonlocal body, body_n, tail_words
            if not body:
                return
            text = section.label + "\n" + "\n".join(body)
            chunks.append(_make_chunk(doc, len(chunks), section.label, first_page, text))
            tail_words = "\n".join(body).split() if last_kind == "text" else []
            body, body_n = [], 0

        for kind, text, page in pieces:
            n = count_tokens(text)
            if body and body_n + n > budget:
                emit()
            if not body:
                first_page = page
                if tail_words and kind == "text" and overlap > 0:
                    keep = min(overlap, max(budget - n, 0), len(tail_words))
                    if keep > 0:
                        carried = " ".join(tail_words[-keep:])
                        body.append(carried)
                        body_n += keep
            body.append(text)
            body_n += n
            last_kind = kind
        emit()
    # ids are ordinal over the whole document
    return [Chunk(id=f"{_slug(doc.source)}-{i:04d}", text=c.text, source=c.source,
                  section=c.section, page=c.page, doc_version=c.doc_version,
                  superseded=c.superseded) for i, c in enumerate(chunks)]


def _chunk_fixed(doc: Document, size: int, overlap: int) -> list[Chunk]:
    words: list[tuple[str, int, str]] = []   # (word, page, best known section)
    section = "Preamble"
    for page in doc.pages:
        for line in page.text.split("\n"):
            label = heading_label(line)
            if label is not None:
                section = label
            words.extend((w, page.page, section) for w in line.split())
    chunks: list[Chunk] = []
    step = size - overlap
    for start in range(0, len(words), step):
        window = words[start:start + size]
        _, first_page, sec = window[0]
        chunks.append(_make_chunk(doc, len(chunks), sec, first_page, " ".join(w for w, _, _ in window)))
        if start + size >= len(words):
            break
    return chunks


def chunk(doc: Document, size: int, overlap: int, strategy: str | None = None) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` words, with `overlap` words shared between neighbours inside a section. Every
    chunk keeps the section heading it sits under, its page, doc_version and superseded."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError(f"need 0 <= overlap < size, got size={size} overlap={overlap}")
    strategy = strategy or os.environ.get("CHUNK_STRATEGY", "structure")
    if strategy == "fixed":
        return _chunk_fixed(doc, size, overlap)
    if strategy == "structure":
        return _chunk_structured(doc, size, overlap)
    raise ValueError(f"unknown CHUNK_STRATEGY {strategy!r}; expected structure or fixed")


def amplification(doc: Document, chunks: list[Chunk]) -> float:
    """Storage amplification: stored words divided by the document's original words."""
    original = sum(count_tokens(p.text) for p in doc.pages)
    stored = sum(count_tokens(c.text) for c in chunks)
    return round(stored / original, 3) if original else 0.0
