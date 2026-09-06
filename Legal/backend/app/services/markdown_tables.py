"""Normalize and parse GitHub-flavored Markdown tables in AI output.

Models often emit broken tables (header + separator collapsed onto one line,
missing pipes on separator rows, ragged columns). This module repairs them
into valid GFM so ``remark-gfm`` / DOCX exporters can render real tables.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
# GFM separator cells need 3+ dashes. `{1,}` treated a lone "-" data cell as a
# separator and split real tables while the model was still streaming them.
_SEP_CELL_RE = re.compile(r"^:?-{3,}:?$")
_UNICODE_DASHES = str.maketrans({"—": "-", "–": "-", "−": "-"})
# Bare dash lines the model dumps instead of a GFM separator row.
_BARE_DASH_RE = re.compile(r"^\s*[-—–−]{3,}\s*$")
# Collapsed header+separator: "| A | B | | :--- | :--- |" or "| A | B || :--- |"
_COLLAPSED_SEP_RE = re.compile(
    r"^(?P<header>\|.+?)\s*\|\s*(?P<sep>\|\s*:?-{2,}.*?)\s*$"
)
_HEADING_RE = re.compile(r"^#{1,6}\s")
_LIST_RE = re.compile(r"^([-*+]|\d+\.)\s")


def looks_like_table_row(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith("```") or s.startswith(">") or _HEADING_RE.match(s):
        return False
    if s.startswith("|"):
        # AI often drops the trailing pipe; still treat as a table row.
        return s.count("|") >= 2
    # Models often omit the leading fence: "Point | Position A | Position B"
    if s.count("|") < 2 or _LIST_RE.match(s):
        return False
    first = s.split("|", 1)[0].strip()
    return 0 < len(first) <= 80


def looks_like_separator_row(line: str) -> bool:
    if not looks_like_table_row(line):
        return False
    cells = split_row(line)
    if not cells:
        return False
    return all(_SEP_CELL_RE.match(c.replace(" ", "")) for c in cells)


def looks_like_bare_dash_line(line: str) -> bool:
    return bool(_BARE_DASH_RE.match(line or ""))


def split_row(line: str) -> list[str]:
    s = line.strip().translate(_UNICODE_DASHES)
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    parts = s.split("|")
    return [c.strip() for c in parts]


def _fence_row(line: str) -> str:
    s = line.strip()
    if not s.startswith("|"):
        s = "| " + s
    if not s.endswith("|"):
        s = s + " |"
    return s


def _row_incomplete(line: str) -> bool:
    """A table row the model wrapped before emitting the closing pipe."""
    s = (line or "").rstrip()
    return bool(s) and looks_like_table_row(s) and not s.endswith("|")


def _is_wrap_continuation(line: str) -> bool:
    """True when a line is leftover cell text, not a new markdown block."""
    s = (line or "").strip()
    if not s or s.startswith("|"):
        return False
    if looks_like_bare_dash_line(s):
        return False
    if s.startswith("```") or s.startswith(">") or _HEADING_RE.match(s) or _LIST_RE.match(s):
        return False
    return True


def _join_wrapped_rows(lines: list[str]) -> list[str]:
    """Stitch cell text that the model wrapped onto the next line.

    Gemini often breaks a row mid-cell::

        | Scope | What losses are covered
        including consequential loss | Cap and carve-outs |
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip() and out and looks_like_table_row(out[-1]):
            nxt = lines[i + 1] if i + 1 < n else ""
            if looks_like_table_row(nxt) or looks_like_bare_dash_line(nxt):
                i += 1
                continue
            if _row_incomplete(out[-1]) and _is_wrap_continuation(nxt):
                i += 1
                continue
        if out and _row_incomplete(out[-1]) and _is_wrap_continuation(line):
            out[-1] = out[-1].rstrip() + " " + line.strip()
            i += 1
            continue
        out.append(line)
        i += 1
    return out


def format_row(cells: list[str], widths: list[int]) -> str:
    padded = []
    for i, width in enumerate(widths):
        cell = cells[i] if i < len(cells) else ""
        padded.append(cell.ljust(width))
    return "| " + " | ".join(padded) + " |"


def format_separator(widths: list[int]) -> str:
    return "| " + " | ".join("-" * max(3, w) for w in widths) + " |"


def _is_sep_cell(cell: str) -> bool:
    return bool(_SEP_CELL_RE.match((cell or "").replace(" ", "")))


def _expand_collapsed_rows(line: str) -> list[str]:
    """Split a line that merged header + separator into two GFM rows."""
    s = line.strip()
    if not looks_like_table_row(s):
        return [line]

    cells = split_row(s)
    if len(cells) < 2:
        return [line]

    # Case A: explicit empty cell then separator cells ("| A | B | | :--- | :--- |")
    sep_start = None
    for i, c in enumerate(cells):
        if c == "" and i + 1 < len(cells) and _is_sep_cell(cells[i + 1]):
            sep_start = i + 1
            break
        if _is_sep_cell(c) and i > 0 and not all(_is_sep_cell(x) for x in cells[:i]):
            # Mixed header + sep cells without empty gap
            sep_start = i
            break

    if sep_start is None:
        # Case B: regex fallback for "… | | :---"
        m = _COLLAPSED_SEP_RE.match(s)
        if m:
            return [m.group("header").rstrip(), m.group("sep")]
        return [line]

    header_cells = [c for c in cells[:sep_start] if c != "" or sep_start == 0]
    # Keep intentional empty trailing header cells only if before sep gap
    header_cells = cells[:sep_start]
    while header_cells and header_cells[-1] == "":
        header_cells.pop()
    sep_cells = [c for c in cells[sep_start:] if c != ""]
    if not header_cells or not sep_cells:
        return [line]
    if not all(_is_sep_cell(c) for c in sep_cells):
        return [line]

    widths = [max(3, len(c)) for c in header_cells]
    # Pad sep to header width
    while len(sep_cells) < len(header_cells):
        sep_cells.append("---")
    sep_cells = sep_cells[: len(header_cells)]
    return [format_row(header_cells, widths), format_separator(widths)]


def _preprocess_lines(text: str) -> list[str]:
    """Expand collapsed rows and drop bare-dash noise adjacent to tables."""
    raw = _join_wrapped_rows(text.splitlines())
    expanded: list[str] = []
    for line in raw:
        if looks_like_table_row(line) and any(_is_sep_cell(c) for c in split_row(line)) and not looks_like_separator_row(line):
            expanded.extend(_expand_collapsed_rows(line))
        else:
            expanded.append(line)

    # Drop bare dash lines that sit inside / next to table blocks.
    out: list[str] = []
    n = len(expanded)
    for i, line in enumerate(expanded):
        if looks_like_bare_dash_line(line):
            prev = expanded[i - 1] if i > 0 else ""
            nxt = expanded[i + 1] if i + 1 < n else ""
            if (
                looks_like_table_row(prev)
                or looks_like_table_row(nxt)
                or looks_like_bare_dash_line(prev)
                or looks_like_bare_dash_line(nxt)
            ):
                continue
        out.append(line)
    return out


def _normalize_table_block(lines: list[str]) -> list[str]:
    """Rebuild one GFM table with aligned columns and a valid separator."""
    rows: list[list[str]] = []
    for line in lines:
        if looks_like_separator_row(line):
            continue
        if looks_like_bare_dash_line(line):
            continue
        cells = split_row(line)
        # Drop all-separator phantom rows that slipped through.
        if cells and all(_is_sep_cell(c) for c in cells):
            continue
        if cells:
            rows.append(cells)
    if not rows:
        return lines

    col_count = max(len(r) for r in rows)
    normalized_rows = [r + [""] * (col_count - len(r)) for r in rows]
    widths = [3] * col_count
    for row in normalized_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell), 3)

    header, *body = normalized_rows
    out = [format_row(header, widths), format_separator(widths)]
    out.extend(format_row(r, widths) for r in body)
    return out


def normalize_markdown_tables(text: str) -> str:
    """Fix misaligned / incomplete Markdown tables in free-form AI text.

    Ensures each table has a header separator and consistent column counts, and
    pads cells so monospace previews line up. Also repairs collapsed
    header+separator lines and strips bare dash noise.
    """
    if not text or "|" not in text:
        return text

    lines = _preprocess_lines(text)
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if looks_like_table_row(lines[i]):
            start = i
            while i < n and (
                looks_like_table_row(lines[i]) or looks_like_bare_dash_line(lines[i])
            ):
                i += 1
            block = [ln for ln in lines[start:i] if not looks_like_bare_dash_line(ln)]
            # Need at least a header; synthesise separator even for a lone header.
            if len(block) >= 1:
                out.extend(_normalize_table_block(block))
            else:
                out.extend(lines[start:i])
            continue
        out.append(lines[i])
        i += 1
    result = "\n".join(out)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def iter_content_segments(text: str) -> Iterator[tuple[str, str | list[list[str]]]]:
    """Yield ``(\"text\", paragraph)`` or ``(\"table\", rows)`` segments.

    Table rows exclude the separator; first row is the header.
    """
    if not text:
        return
    lines = normalize_markdown_tables(text).splitlines()
    buf: list[str] = []
    i = 0
    n = len(lines)

    def flush_text() -> list[tuple[str, str]]:
        nonlocal buf
        if not buf:
            return []
        chunk = "\n".join(buf)
        buf = []
        return [("text", chunk)]

    while i < n:
        if looks_like_table_row(lines[i]):
            yield from flush_text()
            start = i
            while i < n and looks_like_table_row(lines[i]):
                i += 1
            block = lines[start:i]
            rows: list[list[str]] = []
            for line in block:
                if looks_like_separator_row(line):
                    continue
                cells = split_row(line)
                if cells:
                    rows.append(cells)
            if rows:
                col_count = max(len(r) for r in rows)
                rows = [r + [""] * (col_count - len(r)) for r in rows]
                yield ("table", rows)
            else:
                buf.extend(block)
            continue
        buf.append(lines[i])
        i += 1
    yield from flush_text()


def content_has_markdown_table(text: str) -> bool:
    """True when ``text`` contains at least one GFM table block."""
    if not text or "|" not in text:
        return False
    return any(kind == "table" for kind, _ in iter_content_segments(text))
