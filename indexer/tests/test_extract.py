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
                            ["2. Warning", "DC 15 to hide in plain sight."]]))
    doc = extract(str(f), "2026-06", False)
    assert [p.page for p in doc.pages] == [1, 2]
    assert "80 percent" in doc.pages[0].text
    assert "DC 15 to hide" in doc.pages[1].text
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


def test_pdf_heading_lines_are_marked_by_font_size(tmp_path: Path) -> None:
    pdf = tmp_path / "rules.pdf"
    body = "Body text sentence about how the rule works in practice."
    pdf.write_bytes(make_pdf([["#H Help Action", body, body, body, "#H Hide", body, body]]))
    text = extract(str(pdf), "2024", False).pages[0].text
    assert "## Help Action" in text
    assert "## Hide" in text
    assert "## Body text" not in text


def _line(text: str, size: float, font: str = "Body", top: float = 100.0) -> dict:
    return {"text": text, "top": top, "chars": [{"text": ch, "size": size, "fontname": font} for ch in text]}


def test_slightly_bigger_bold_line_is_a_heading() -> None:
    from pipeline.extract import _lines_to_text
    out = _lines_to_text([_line("Exhaustion", 10.8, "GillSans-SemiBold"), _line("A body line", 9.8)], 9.8, 800.0)
    assert out.split("\n")[0] == "## Exhaustion"


def test_slightly_bigger_regular_line_is_not_a_heading() -> None:
    from pipeline.extract import _lines_to_text
    assert not _lines_to_text([_line("Some text", 10.8, "Calibri")], 9.8, 800.0).startswith("##")


def test_footer_is_never_a_heading_even_when_bold_and_big() -> None:
    from pipeline.extract import _lines_to_text
    footer = _line("System Reference Document 5.1 352", 12.0, "GillSans-SemiBold", top=790.0)
    assert not _lines_to_text([footer], 9.8, 800.0).startswith("##")


def test_statblock_subheads_stay_plain_text_when_only_bold_marks_them() -> None:
    from pipeline.extract import _lines_to_text
    assert not _lines_to_text([_line("Actions", 10.8, "GillSans-SemiBold")], 9.8, 800.0).startswith("##")
