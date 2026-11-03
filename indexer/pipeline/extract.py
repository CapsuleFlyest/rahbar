"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page.

PDF pages are read with pdfplumber. Tables are located separately and rendered as
Markdown tables, so columns do not come out jumbled. Pages with no text layer are
rendered to an image and OCR'd with Tesseract (needs tesseract-ocr and poppler-utils
in the image). A page that cannot be recovered is kept empty and logged: an honest
loss, not a silent one.
"""

from __future__ import annotations

import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .models import Document, Page

MIN_TEXT_CHARS = 20          # fewer non-space characters than this = no usable text layer
DEFAULT_OCR_LANG = "eng"
DEFAULT_OCR_DPI = 300


def _log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer.extract", "msg": msg, **fields}),
          file=sys.stdout, flush=True)


def _norm_cell(cell: object) -> str:
    return re.sub(r"\s+", " ", str(cell or "")).strip().replace("|", "/")


def table_to_markdown(rows: list[list[Any]]) -> str:
    """Render a table (list of rows) as a Markdown table: header, separator, body."""
    cleaned = [[_norm_cell(c) for c in row] for row in rows if row]
    cleaned = [r for r in cleaned if any(r)]
    if not cleaned:
        return ""
    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]
    lines = ["| " + " | ".join(cleaned[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in cleaned[1:]]
    return "\n".join(lines)


def ocr_page(path: str, page_number: int, lang: str = DEFAULT_OCR_LANG,
             dpi: int = DEFAULT_OCR_DPI) -> str:
    """OCR one 1-based PDF page. Module-level so tests can monkeypatch it."""
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(path, first_page=page_number, last_page=page_number, dpi=dpi)
    try:
        return "\n".join(pytesseract.image_to_string(img, lang=lang) for img in images)
    finally:
        for img in images:
            img.close()


def _page_text_and_tables(page: Any) -> str:
    """Text outside tables, followed by each table as Markdown."""
    tables = []
    try:
        tables = list(page.find_tables())
    except Exception:  # a malformed table must not lose the page's text
        tables = []
    body = page
    for table in tables:
        try:
            body = body.outside_bbox(table.bbox)
        except Exception:
            pass
    text = body.extract_text() or ""
    rendered = []
    for table in tables:
        try:
            md = table_to_markdown(table.extract())
        except Exception:
            md = ""
        if md:
            rendered.append(md)
    return "\n\n".join(p for p in [text.strip(), *rendered] if p)


def _extract_pdf(path: str, doc: Document, ocr_lang: str, ocr_dpi: int) -> None:
    import pdfplumber

    ocr_pages: list[int] = []
    empty_pages: list[int] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = _page_text_and_tables(page)
            has_images = bool(getattr(page, "images", None))
            ocr = False
            if len(re.sub(r"\s", "", text)) < MIN_TEXT_CHARS and (has_images or not text.strip()):
                try:
                    text = ocr_page(path, number, ocr_lang, ocr_dpi)
                    ocr = True
                    ocr_pages.append(number)
                except Exception as exc:  # keep the page empty: an honest, logged loss
                    _log("ocr failed", source=doc.source, page=number, error=str(exc))
                    text = ""
                if not text.strip():
                    empty_pages.append(number)
            doc.pages.append(Page(source=doc.source, page=number, text=text, ocr=ocr))
            page.flush_cache()
    if ocr_pages or empty_pages:
        _log("ocr summary", source=doc.source, ocr_pages=ocr_pages, empty_pages=empty_pages)


_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript"}
_BLOCK_TAGS = {"p", "div", "li", "br", "section", "article", "ul", "ol", "table"}
_HEADINGS = {f"h{i}": "#" * i for i in range(1, 7)}


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.buf: list[str] = []
        self.skip = 0
        self.heading: str | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.table_rows: list[list[str]] = []

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if text:
            self.lines.append(f"{self.heading} {text}" if self.heading else text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skip += 1
        if self.skip:
            return
        if tag in _HEADINGS:
            self._flush()
            self.heading = _HEADINGS[tag]
        elif tag == "table":
            self._flush()
            self.table_rows = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in _BLOCK_TAGS and self.cell is None:
            self._flush()
            if tag in ("p", "div"):
                self.lines.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _HEADINGS:
            self._flush()
            self.heading = None
            self.lines.append("")
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table_rows.append(self.row)
            self.row = None
        elif tag == "table":
            md = table_to_markdown(self.table_rows)
            if md:
                self.lines += ["", md, ""]
            self.table_rows = []
        elif tag in _BLOCK_TAGS and self.cell is None:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        else:
            self.buf.append(data)

    def text(self) -> str:
        self._flush()
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.lines)).strip()


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    return parser.text()


def strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


def extract(path: str, doc_version: str, superseded: bool, *,
            ocr_lang: str = DEFAULT_OCR_LANG, ocr_dpi: int = DEFAULT_OCR_DPI) -> Document:
    """Return the document's text page by page.

    Pages with no text layer are OCR'd and marked ocr=True. HTML and Markdown documents
    become a single page (page 1)."""
    p = Path(path)
    doc = Document(source=p.name, doc_version=doc_version, superseded=superseded)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        _extract_pdf(str(p), doc, ocr_lang, ocr_dpi)
    elif suffix in (".html", ".htm"):
        text = html_to_text(p.read_text(encoding="utf-8", errors="replace"))
        doc.pages.append(Page(source=doc.source, page=1, text=text))
    elif suffix in (".md", ".txt"):
        text = strip_front_matter(p.read_text(encoding="utf-8", errors="replace"))
        doc.pages.append(Page(source=doc.source, page=1, text=text))
    else:
        raise ValueError(f"unsupported document type {suffix!r}: {p.name}")
    return doc
