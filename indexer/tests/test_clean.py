from __future__ import annotations

from pipeline.clean import RULES, clean
from pipeline.models import Document, Page


def make_doc(texts: list[str]) -> Document:
    pages = [Page(source="d.pdf", page=i + 1, text=t) for i, t in enumerate(texts)]
    return Document(source="d.pdf", doc_version="2026", superseded=False, pages=pages)


def test_running_headers_and_footers_are_removed() -> None:
    bodies = ["Attendance is compulsory.", "Fees are due in August.", "Grades are final.",
              "Mind flayers are not covered."]
    texts = [f"System Reference Document 5.2.1\n{b}\nConfidential {i}" for i, b in enumerate(bodies)]
    out = clean(make_doc(texts))
    for page in out.pages:
        assert "System Reference Document" not in page.text
        assert "Confidential" not in page.text
    assert [p.text for p in out.pages] == bodies


def test_repeats_on_fewer_than_three_pages_are_kept() -> None:
    out = clean(make_doc(["Same line\nA", "Same line\nB"]))
    assert "Same line" in out.pages[0].text


def test_bare_page_numbers_are_removed() -> None:
    out = clean(make_doc(["Text one\n12\nPage 3 of 53\n- 4 -\nText two"]))
    assert out.pages[0].text == "Text one\nText two"


def test_hyphenated_line_break_is_joined_only_before_lowercase() -> None:
    out = clean(make_doc(["The exam-\nination is held.\nNon-\nStandard stays."]))
    text = out.pages[0].text
    assert "examination is held." in text
    assert "Non-\nStandard" in text


def test_clause_numbers_headings_and_table_pipes_survive() -> None:
    body = "5.4 Exhaustion\n(a) DC 15 to hide\n| Plate | 1,500 |\n| --- | --- |"
    out = clean(make_doc([body] * 4))
    text = out.pages[0].text
    assert "5.4 Exhaustion" in text
    assert "(a) DC 15 to hide" in text
    assert "| Plate | 1,500 |" in text


def test_whitespace_and_control_characters_are_normalised() -> None:
    out = clean(make_doc(["a  \t b\x00\x0c\n\n\n\n\nc"]))
    assert out.pages[0].text == "a b\n\nc"


def test_clean_keeps_metadata_and_documents_its_rules() -> None:
    doc = make_doc(["x"])
    doc.superseded = True
    out = clean(doc)
    assert (out.source, out.doc_version, out.superseded) == ("d.pdf", "2026", True)
    assert len(RULES) >= 4
