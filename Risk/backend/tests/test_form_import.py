"""Unit tests for VDD workbook -> form template parsing.

The sheet's columns are not contiguous: cells are merged into groups, so
Parameter spans B:D and Response spans F:I, leaving Type at E and Additional
Remarks at J. Reading five cells from column A picked up three empty columns and
mistook Type for Remarks, which silently cost every Yes/No control, every
long-text box, and all of the sheet's guidance. These tests pin the detected
layout and the resulting schema so that cannot regress.
"""
import io
from collections import Counter
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.form_import import (
    _detect_columns,
    _infer_field_type,
    _is_type_hint,
    list_workbook_sheets,
    parse_vdd_sheet,
)

WORKBOOK = Path(__file__).resolve().parents[2] / "1 Vendor Due Diligence - [Vendor Name].xlsx"
VDD_SHEET_INDEX = 1

pytestmark = pytest.mark.skipif(not WORKBOOK.exists(), reason="VDD workbook not present")


@pytest.fixture(scope="module")
def workbook_bytes() -> bytes:
    return WORKBOOK.read_bytes()


@pytest.fixture(scope="module")
def schema(workbook_bytes: bytes) -> dict:
    return parse_vdd_sheet(workbook_bytes, sheet_index=VDD_SHEET_INDEX)["schema"]


@pytest.fixture(scope="module")
def fields(schema: dict) -> list[dict]:
    return [f for s in schema["sections"] for f in s["fields"]]


def test_columns_are_detected_from_the_header_not_assumed_contiguous(workbook_bytes):
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(workbook_bytes), data_only=True)
    columns = _detect_columns(wb.worksheets[VDD_SHEET_INDEX])
    wb.close()

    # Type/Response/Remarks are NOT at 2/3/4 — that assumption was the bug.
    assert columns == {"sl_no": 0, "parameter": 1, "param_type": 4, "response": 5, "remarks": 9}


def test_the_sheets_own_section_titles_survive(schema):
    """Type ("General information") must not flatten the real sections."""
    titles = [s["title"] for s in schema["sections"]]

    assert len(titles) == 7
    assert titles[0].startswith("Engagement Overview")
    assert "Reputation" in titles
    assert "General information" not in titles


def test_every_numbered_question_becomes_a_field(fields):
    assert len(fields) == 38
    assert all(f["label"] and f["id"] for f in fields)


def test_answer_controls_are_inferred_rather_than_all_text(fields):
    """Previously every one of the 38 fields imported as plain `text`."""
    types = Counter(f["type"] for f in fields)

    assert types["yes_no"] == 17
    assert types["textarea"] == 8
    assert types["text"] == 13
    assert all(f.get("options") == ["Yes", "No"] for f in fields if f["type"] == "yes_no")


def test_guidance_reaches_help_text(fields):
    helped = [f for f in fields if f.get("help_text")]

    assert len(helped) == 6
    examples = [f["help_text"] for f in helped if "example" in f["help_text"].lower()]
    assert len(examples) == 2, "the two worked examples are the most valuable guidance"
    assert any(h.startswith("Below Example for Reference:") for h in examples)


def test_type_hints_never_leak_into_help_text(fields):
    """"Freetext"/"Yes" declare the answer type; shown as advice they are noise."""
    for f in fields:
        assert not _is_type_hint(f.get("help_text") or "")


def test_guidance_never_becomes_a_placeholder(fields):
    """Multi-line worked examples would be unreadable as ghost text."""
    assert all(not f.get("placeholder") for f in fields)


@pytest.mark.parametrize(
    "response,expected",
    [
        ("Yes", "yes_no"),
        ("No", "yes_no"),
        ("Freetext", "textarea"),
        ("free text", "textarea"),
        ("x" * 130, "textarea"),
        ("India", "text"),
        ("", "text"),
    ],
)
def test_field_type_inference(response, expected):
    assert _infer_field_type("Some question", response, "") == expected


# --------------------------------------------------------------------------
# Layouts other than this workbook's
# --------------------------------------------------------------------------


def _sheet_to_bytes(rows: list[list], title: str = "Sheet1") -> bytes:
    wb = Workbook()
    wb.active.title = title
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def test_a_contiguous_five_column_sheet_still_parses():
    data = _sheet_to_bytes([
        ["Sl. No.", "Parameter", "Type", "Response", "Remarks"],
        ["Section One", "", "", "", ""],
        ["1.0", "Is data encrypted?", "Security", "Yes", ""],
        ["2.0", "Describe the service", "Security", "Please provide detail", ""],
    ])
    schema = parse_vdd_sheet(data, sheet_index=0)["schema"]
    fields = [f for s in schema["sections"] for f in s["fields"]]

    assert [s["title"] for s in schema["sections"]] == ["Section One"]
    assert fields[0]["type"] == "yes_no"
    assert fields[1]["help_text"] == "Please provide detail"


def test_a_sheet_with_no_header_row_falls_back_to_positional_columns():
    data = _sheet_to_bytes([
        ["Section One", "", "", "", ""],
        ["1.0", "Is data encrypted?", "Security", "Yes", ""],
    ])
    fields = [
        f for s in parse_vdd_sheet(data, sheet_index=0)["schema"]["sections"] for f in s["fields"]
    ]

    assert len(fields) == 1
    assert fields[0]["type"] == "yes_no"


def test_type_groups_sections_only_when_the_sheet_names_none():
    """Back-compat: a sheet whose only structure is the Type column."""
    data = _sheet_to_bytes([
        ["Sl. No.", "Parameter", "Type", "Response", "Remarks"],
        ["1.0", "Question A", "Security", "", ""],
        ["2.0", "Question B", "Commercial", "", ""],
    ])
    schema = parse_vdd_sheet(data, sheet_index=0)["schema"]

    assert [s["title"] for s in schema["sections"]] == ["Security", "Commercial"]


def test_sheet_listing_is_unaffected(workbook_bytes):
    sheets = list_workbook_sheets(workbook_bytes)

    assert sheets[VDD_SHEET_INDEX]["name"] == "Vendor Due Diligence Assessment"
    assert sheets[VDD_SHEET_INDEX]["row_count"] > 0


def test_out_of_range_sheet_index_is_rejected(workbook_bytes):
    with pytest.raises(ValueError, match="out of range"):
        parse_vdd_sheet(workbook_bytes, sheet_index=99)
