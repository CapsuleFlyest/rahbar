from __future__ import annotations

from pathlib import Path

import pytest
from pipeline import extract as ex
from pipeline.extract import extract, html_to_text, table_to_markdown

from tests.pdfutil import make_pdf


def test_markdown_front_matter_is_stripped(tmp_path: Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("---\ndoc_version: 2026\n---\n# Title\n\nBody", encoding="utf-8")
    doc = extract(str(f), "2026", False)
    assert doc.source == "a.md"
    assert len(doc.pages) == 1
    assert doc.pages[0].text.startswith("# Title")
    assert "doc_version" not in doc.pages[0].text


def test_html_headings_tables_and_boilerplate() -> None:
    html = ("<html><nav>Menu</nav><script>x=1</script><h2>Fees</h2><p>Per credit hour.</p>"
            "<table><tr><th>Programme</th><th>Fee</th></tr>"
            "<tr><td>BS</td><td>10,000</td></tr></table><footer>Copyright</footer></html>")
    text = html_to_text(html)
    assert "## Fees" in text
    assert "| Programme | Fee |" in text
    assert "| BS | 10,000 |" in text
    assert "Menu" not in text and "Copyright" not in text and "x=1" not in text


def test_html_file_becomes_one_page(tmp_path: Path) -> None:
    f = tmp_path / "p.html"
    f.write_text("<h1>Grading</h1><p>A = 4.0</p>", encoding="utf-8")
    doc = extract(str(f), "2026", False)
    assert len(doc.pages) == 1 and "# Grading" in doc.pages[0].text


def test_table_to_markdown_normalises_cells() -> None:
    md = table_to_markdown([["Charge", None], ["Late  fee", "3,000 | PKR"]])
    assert md.splitlines() == ["| Charge |  |", "| --- | --- |", "| Late fee | 3,000 / PKR |"]


def test_pdf_text_is_extracted_page_by_page(tmp_path: Path) -> None:
    f = tmp_path / "rules.pdf"
    f.write_bytes(make_pdf([["1. Attendance", "Students need 80 percent attendance."],
                            ["2. Warning", "CGPA below 2.00 means warning."]]))
    doc = extract(str(f), "2026-06", False)
    assert [p.page for p in doc.pages] == [1, 2]
    assert "80 percent" in doc.pages[0].text
    assert "CGPA below 2.00" in doc.pages[1].text
    assert not any(p.ocr for p in doc.pages)


def test_blank_page_goes_through_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_ocr(path: str, number: int, lang: str = "eng", dpi: int = 300) -> str:
        calls.append(number)
        return "Recovered by OCR: start-up policy clause 7"

    monkeypatch.setattr(ex, "ocr_page", fake_ocr)
    f = tmp_path / "scan.pdf"
    f.write_bytes(make_pdf([["A normal text page with plenty of words."], []]))
    doc = extract(str(f), "2022-05", False)
    assert calls == [2]
    assert doc.pages[0].ocr is False
    assert doc.pages[1].ocr is True and "Recovered by OCR" in doc.pages[1].text


def test_failed_ocr_keeps_an_empty_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object, **kwargs: object) -> str:
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr(ex, "ocr_page", broken)
    f = tmp_path / "scan.pdf"
    f.write_bytes(make_pdf([[]]))
    doc = extract(str(f), "2022-05", False)
    assert doc.pages[0].text == "" and doc.pages[0].ocr is False


def test_unsupported_type_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "x.docx"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        extract(str(f), "1", False)
