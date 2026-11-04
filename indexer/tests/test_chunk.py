from __future__ import annotations

import pytest

from pipeline.chunk import heading_label


@pytest.mark.parametrize(
    "line",
    ["5.1 3", "2 +2", "20 Acid", "4 14 4 3 3 3 2 1 1", "1 System Reference Document 5.2.1"],
)
def test_table_rows_and_footers_are_not_headings(line: str) -> None:
    assert heading_label(line) is None


@pytest.mark.parametrize("line", ["5.4 Academic Warning", "1. Attendance", "## Help Action"])
def test_real_headings_are_still_headings(line: str) -> None:
    assert heading_label(line) is not None
