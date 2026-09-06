"""Tests for Markdown table normalization used by Ask AI to Edit + LawGenie."""

from app.services.markdown_tables import normalize_markdown_tables, iter_content_segments


def test_normalizes_ragged_columns_and_adds_separator():
    raw = """\
| Point | Position A | Position B
| Liability | 12 months | Unlimited | High |
| Indemnity | Mutual | One-way |
"""
    fixed = normalize_markdown_tables(raw)
    lines = [ln for ln in fixed.splitlines() if ln.strip()]
    assert lines[0].startswith("| Point")
    assert set(lines[1].replace(" ", "")) <= set("|:-")
    assert lines[1].count("|") == lines[0].count("|")
    # Every body row has the same pipe count as the header.
    for line in lines[2:]:
        assert line.count("|") == lines[0].count("|")


def test_leaves_non_table_text_alone():
    text = "Clause 1. The parties agree.\n\nClause 2. Liability."
    assert normalize_markdown_tables(text) == text


def test_iter_segments_splits_table():
    text = "Intro\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nOutro"
    segs = list(iter_content_segments(normalize_markdown_tables(text)))
    kinds = [k for k, _ in segs]
    assert "table" in kinds
    table = next(p for k, p in segs if k == "table")
    assert table[0] == ["A", "B"]
    assert table[1] == ["1", "2"]


def test_repairs_collapsed_header_and_separator():
    """Model often merges header + separator: '| A | B | | :--- | :--- |'."""
    raw = (
        "Intro\n\n"
        "| Aspect | Description | Key Considerations for JFPSL | | :----------------- | :-----------------\n"
        "-------------------\n"
        "-------------------\n"
        "| Scope | What losses are covered | Cap and carve-outs |\n"
        "| Duty to defend | Who pays defence costs | Trigger events |\n"
    )
    fixed = normalize_markdown_tables(raw)
    lines = [ln for ln in fixed.splitlines() if ln.strip()]
    header = next(ln for ln in lines if "Aspect" in ln)
    sep = lines[lines.index(header) + 1]
    assert "Description" in header
    assert set(sep.replace(" ", "")) <= set("|:-")
    assert header.count("|") == sep.count("|")
    assert any("Scope" in ln for ln in lines)
    assert header != sep
    assert "||" not in header


def test_joins_wrapped_cell_onto_previous_row():
    raw = (
        "| Point | Position A | Note |\n"
        "| --- | --- | --- |\n"
        "| Scope | What losses are covered\n"
        "including consequential loss | Cap and carve-outs |\n"
    )
    fixed = normalize_markdown_tables(raw)
    assert "What losses are covered including consequential loss" in fixed
    lines = [ln for ln in fixed.splitlines() if ln.strip()]
    body = [ln for ln in lines if "Scope" in ln]
    assert len(body) == 1
    assert body[0].count("|") == lines[0].count("|")


def test_fences_rows_missing_leading_pipe():
    raw = (
        "Point | Position A | Position B\n"
        "--- | --- | ---\n"
        "Liability | 12 months | Unlimited\n"
    )
    fixed = normalize_markdown_tables(raw)
    lines = [ln for ln in fixed.splitlines() if ln.strip()]
    assert lines[0].startswith("|")
    assert all(ln.startswith("|") and ln.endswith("|") for ln in lines)
    assert "Liability" in fixed


def test_skips_blank_line_inside_table():
    raw = (
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
        "\n"
        "| 3 | 4 |\n"
    )
    segs = list(iter_content_segments(normalize_markdown_tables(raw)))
    tables = [p for k, p in segs if k == "table"]
    assert len(tables) == 1
    assert tables[0][-1] == ["3", "4"]
