import io
import re
from pathlib import Path


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".txt") or lower.endswith(".md"):
        text = data.decode("utf-8", errors="replace")
    elif lower.endswith(".docx"):
        try:
            text = _extract_docx_text(data)
        except Exception:
            text = data.decode("utf-8", errors="replace")
    elif lower.endswith(".pdf"):
        try:
            text = _extract_pdf_text(data)
        except Exception:
            text = ""
    elif lower.endswith(".xlsx"):
        try:
            text = _extract_xlsx_text(data)
        except Exception:
            # Deliberately not the .docx branch's decode fallback: an .xlsx is a
            # zip container, so decoding it yields the PK\x03\x04 mojibake this
            # branch exists to prevent. Empty is the honest answer.
            text = ""
    else:
        # This used to be a utf-8 decode, which turned every unrecognised binary
        # into pages of mojibake and handed it to the classifier as if it were
        # the form. A clear rejection beats a confident nonsense answer.
        raise ValueError(f"Unsupported file type: {Path(filename).suffix or filename}")
    # A ticked checkbox marks the chosen answer just as a highlight does — run a
    # final glyph pass so both signals land as the same [SELECTED: ...] marker.
    return _mark_checked_boxes(text)


# A checked box (☒/☑) or a checkmark (✓/✔) next to an option means that option
# was chosen. The empty box (□/▢/☐) is deliberately excluded so this never
# re-marks a highlighted answer, which keeps its empty box.
_CHECKED_GLYPHS = "☑☒⊠✔✓✅🗹"
_TICK_RE = re.compile(
    # label = up to 40 chars right before the glyph, not crossing a cell
    # separator, another marker, or any box glyph (so "High □ Medium ☒" grabs
    # only "Medium", not "High □ Medium")
    r"([^|:\[\]□▢☐" + _CHECKED_GLYPHS + r"\n]{1,40}?)\s*([" + _CHECKED_GLYPHS + r"])"
)


def _mark_checked_boxes(text: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        label = m.group(1).strip()
        glyph = m.group(2)
        return f"[SELECTED: {label} {glyph}]" if label else f"[SELECTED: {glyph}]"

    return _TICK_RE.sub(repl, text)


# ---- Selected-answer summary --------------------------------------------
# extract_text() marks every chosen option with a [SELECTED: ...] wrapper.
# summarize_selected_answers() collapses that full form text down to just the
# questions the reviewer answered and the option each chose, so the classifier
# sees a short, unambiguous "Question: Answer" list instead of the whole form.

_ALL_BOX_GLYPHS = "□▢☐" + _CHECKED_GLYPHS
_BOX_RE = re.compile("[" + _ALL_BOX_GLYPHS + "]")
_SELECTED_RE = re.compile(r"\[SELECTED:\s*([^\]]*?)\s*\]")
# option tokens that must never be mistaken for a question label
_OPTION_WORDS = {"yes", "no", "very high", "high", "medium", "low", "na", "n/a"}


def summarize_selected_answers(text: str) -> str:
    """Reduce extracted form text to one 'Question: Answer' line per answered
    question, using the [SELECTED: ...] markers extract_text() leaves behind.

    Returns '' when the text has no markers at all, so callers can fall back to
    sending the full text — a form with no detected answers is better sent whole
    than sent blank.
    """
    lines = text.split("\n")
    pairs: list[str] = []
    for i, line in enumerate(lines):
        selected = _SELECTED_RE.findall(line)
        if not selected:
            continue
        answer = ", ".join(a for a in (_strip_boxes(s) for s in selected) if a)
        if not answer:
            continue
        question = _question_for(line, lines, i)
        pairs.append(f"{question}: {answer}" if question else answer)
    return "\n".join(pairs)


def _strip_boxes(s: str) -> str:
    return _BOX_RE.sub("", s).strip(" \t:|-").strip()


def _is_wordy(s: str) -> bool:
    # a real question label has a few letters and isn't a bare option token
    return len(re.sub(r"[^A-Za-z]", "", s)) >= 3 and s.lower() not in _OPTION_WORDS


# a line that ends a question: blank, an answer line (starts with ':', or holds a
# checkbox/[SELECTED] marker), or a section heading like "II." / "A)" / "1.".
_HEADING_RE = re.compile(r"^\s*(?:[IVXLC]+|[A-Z]|\d+)[.)]\s")


def _is_boundary(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith(":"):
        return True
    if _SELECTED_RE.search(line) or _BOX_RE.search(line):
        return True
    return bool(_HEADING_RE.match(s))


def _question_for(line: str, lines: list[str], idx: int) -> str:
    # inline form ("IT outsourcing: Yes □ [SELECTED: No □]"): the label is the text
    # before the first ':'/'|' — but only when such a separator is actually present,
    # so an options-only answer line ("Very high □ ... [SELECTED: Low □]") is not
    # mistaken for a label.
    no_sel = _SELECTED_RE.sub("", line)
    head = _strip_boxes(re.split(r"[:|]", no_sel, 1)[0]) if (":" in no_sel or "|" in no_sel) else ""
    if not _is_wordy(head):
        head = ""
    # gather the question's own (possibly wrapped) lines sitting above the answer,
    # stopping at the previous answer/heading/blank so we get the whole question
    # ("Does the service provider have DR\nmeasures in place?") not just its last line.
    collected: list[str] = []
    for j in range(idx - 1, -1, -1):
        if _is_boundary(lines[j]):
            break
        cand = _strip_boxes(re.split(r"[|]", lines[j], 1)[0])
        if not cand:
            break
        collected.append(cand)
    collected.reverse()
    if head:
        collected.append(head)
    return re.sub(r"\s+", " ", " ".join(collected)).strip()


# ---- Canonical field extraction -----------------------------------------
# the client outsourcing forms follow a fixed template. For classification we don't
# send the whole form — only a curated set of fields that appear in every form,
# each with its answer. The full form text is still stored for audit; this only
# shapes what the classifier sees.
#
# How it works: every field is laid out as "Label : value". We locate each known
# label in the extracted text (canonical fields we output + other template labels
# used only as boundaries) and take the text between a canonical label and the
# next label as its value. Within that value the answer is the option the reviewer
# marked — either a ticked ☑ box or a highlight, both of which extract_text()
# already wrapped in [SELECTED: ...] — or, for free-text fields, the text itself.

# (regex, output label). Order doesn't matter; matched by position in the text.
# Entity word (Company/NBFC/Bank) and spacing/line-wraps are kept flexible.
_CANONICAL_FIELDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"name\s+of\s+the\s+activity", re.I), "Name of the activity"),
    (re.compile(r"(?:vendor\s+name|name\s+of\s+the\s+vendor)", re.I), "Vendor Name"),
    (re.compile(r"purpose\s+for\s+outsourcing(?:\s+in\s+detail)?", re.I), "Purpose for outsourcing"),
    (re.compile(r"activity\s+scope(?:\s+in\s+detail)?", re.I), "Activity scope"),
    (re.compile(r"data\s*/?\s*application\s+be\s+hosted(?:\s+with\s+the\s+service\s+provider)?", re.I), "Data/application hosted with service provider"),
    (re.compile(r"dr\s+measures\s+in\s+place", re.I), "Service provider has DR measures"),
    (re.compile(r"(?:has\s+the\s+)?dr\s+been\s+tested", re.I), "DR tested"),
    (re.compile(r"proposal\s+details", re.I), "Proposal details"),
    (re.compile(r"rationale\s+for\s+outsourcing", re.I), "Rationale for outsourcing"),
    (re.compile(r"nature\s+of\s+information\s+proposed\s+to\s+be\s+exchanged(?:\s+with\s+the\s+service\s+provider)?", re.I), "Nature of information exchanged"),
    (re.compile(r"mode\s+of\s+information\s+exchange", re.I), "Mode of information exchange"),
    (re.compile(r"criteria\s+for\s+selection\s+of\s+service\s+provider", re.I), "Criteria for selection of service provider"),
]

# Other template labels, matched only to bound a canonical field's value so it
# doesn't run into the next field. Not emitted.
_BOUNDARY_FIELDS: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"proposal\s+owner",
        r"(?:is\s+the\s+)?process\s+to\s+be\s+followed\s+documented",
        r"in\s+case\s+process\s+is\s+not\s+documented",
        r"it\s+(?:or\s+financial\s+)?outsourcing",
        r"materiality\s+assessment",
        r"risk\s+level\s+of\s+the\s+activity",
        r"unique\s+payment\s+code",
        r"sensitive\s+data\s+to\s+be\s+outsourced",
        r"does\s+the\s+activity\s+involve\s+service\s+provider",
        r"channel\s+of\s+communication",
        r"process\s+for\s+registering\s+customer\s+complaints",
        r"does\s+the\s+activity\s+name\s+commensurate",
        r"has\s+any\s+core\s+function",
        r"information\s+be\s+shared\s+with\s+the\s+service\s+provider",
        r"mitigation\s+put\s+in\s+place",
        r"application\s+tiering",
        r"cyber\s+insurance",
        r"conditions\s+stipulated\s+by\s+(?:isg|infosec)",
        r"details\s+of\s+the\s+actionable",
        r"key\s+risks\s+and\s+mitigation",
        r"service\s+provider\s+identified",
        r"empanelled\s+in\s+the\s+next\s+one\s+year",
        r"operating\s+from\s+the\b",
        r"any\s+further\s+sub-?contracting",
        r"date\s+of\s+commencement",
        r"recommended\s+by",
        r"approved\s+by",
        # Section headings ("IV. Rationale…") at the start of a line, so a field's
        # value stops cleanly before the next section. Stop at the space after the
        # numeral (not into the heading word) so a canonical field whose label
        # follows the numeral — "III. Proposal details" — is still matched.
        r"(?m)^\s*(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s",
    ]
]


# Zero-width / format characters PDF extraction sprinkles in (after bullets,
# numerals, justified text). They're invisible but break "\s"-based boundary
# matching -- e.g. "IV." followed by U+200B isn't caught by r"IV\.\s". Strip
_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


def _normalize_invisible(text: str) -> str:
    return _INVISIBLE_RE.sub("", text.replace("\u00a0", " "))


def _unwrap_with_selection(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Strip the [SELECTED: X] wrappers back to plain text (so labels match even
    when highlighted), while recording the character ranges that were selected —
    that's how we know which option the reviewer picked, for both ticked-box and
    highlight-only forms."""
    parts: list[str] = []
    selected: list[tuple[int, int]] = []
    pos = 0
    last = 0
    for m in _SELECTED_RE.finditer(text):
        before = text[last:m.start()]
        parts.append(before)
        pos += len(before)
        inner = m.group(1)
        parts.append(inner)
        selected.append((pos, pos + len(inner)))
        pos += len(inner)
        last = m.end()
    parts.append(text[last:])
    return "".join(parts), selected


def _clean_value(s: str) -> str:
    return re.sub(r"\s+", " ", _BOX_RE.sub("", s)).strip(" \t:|-").strip()


def _resolve_answer(plain: str, start: int, end: int, selected: list[tuple[int, int]]) -> str:
    """The answer for a field's value span: the reviewer-selected option(s) if any
    fall inside the span, else the free-text value."""
    picks: list[str] = []
    for s, e in selected:
        if s >= start and e <= end:
            v = _clean_value(plain[s:e])
            if v and v not in picks:
                picks.append(v)
    if picks:
        return ", ".join(picks)
    return _clean_value(plain[start:end])


def extract_canonical_fields(text: str) -> str:
    """Reduce a full form to the canonical 'Label: answer' lines the classifier
    should see. Returns '' if none of the canonical fields are found (caller then
    falls back to the full text)."""
    plain, selected = _unwrap_with_selection(_normalize_invisible(text))

    anchors: list[tuple[int, int, str | None]] = []
    for rx, label in _CANONICAL_FIELDS:
        m = rx.search(plain)
        if m:
            anchors.append((m.start(), m.end(), label))
    for rx in _BOUNDARY_FIELDS:
        for m in rx.finditer(plain):
            anchors.append((m.start(), m.end(), None))
    anchors.sort(key=lambda a: a[0])

    # Drop anchors that overlap an earlier one (keep the first at each position).
    deduped: list[tuple[int, int, str | None]] = []
    last_end = -1
    for s, e, label in anchors:
        if s < last_end:
            continue
        deduped.append((s, e, label))
        last_end = e

    lines: list[str] = []
    for i, (s, e, label) in enumerate(deduped):
        if label is None:
            continue
        span_end = deduped[i + 1][0] if i + 1 < len(deduped) else len(plain)
        answer = _resolve_answer(plain, e, span_end, selected)
        if answer:
            lines.append(f"{label}: {answer}")
    return "\n".join(lines)


def _extract_docx_text(data: bytes) -> str:
    from docx import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = DocxDocument(io.BytesIO(data))
    lines: list[str] = []
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            text = _mark_paragraph(block)
            if text.strip():
                lines.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [_mark_cell(c) for c in row.cells]
                if any(c.strip() for c in cells):
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


def _mark_cell(cell) -> str:
    # Cell.text joins its paragraphs with "\n"; keep that but mark highlighted
    # runs so the answer chosen on the form survives extraction.
    return "\n".join(_mark_paragraph(p) for p in cell.paragraphs).strip()


def _mark_paragraph(paragraph) -> str:
    # Word carries the reviewer's answer as a highlight on the chosen run (e.g.
    # the yellow "No □"), which .text silently drops. Wrap highlighted runs in
    # the same [SELECTED: ...] marker the PDF path uses so the prompt's FORM
    # ANSWERS rule can read them. Unhighlighted docs are unaffected — every run
    # just concatenates back to the original text.
    parts: list[str] = []
    for run in paragraph.runs:
        if not run.text:
            continue
        if _run_highlighted(run):
            parts.append(f"[SELECTED: {run.text.strip()}]")
        else:
            parts.append(run.text)
    text = "".join(parts)
    # a highlighted "No" and the checkbox glyph after it are often separate
    # runs — merge "[SELECTED: No] [SELECTED: □]" into one marker
    return re.sub(
        r"\[SELECTED: ([^\]]+)\]\s*\[SELECTED: ([□▢☐])\]",
        r"[SELECTED: \1 \2]",
        text,
    )


def _run_highlighted(run) -> bool:
    from docx.oxml.ns import qn

    # Word's text-highlight (the marker-pen colour reviewers apply to answers)
    try:
        if run.font.highlight_color is not None:
            return True
    except Exception:
        pass
    # some templates use run/paragraph shading (w:shd fill) instead — treat any
    # non-white, non-auto fill as a highlight
    rpr = run._element.rPr
    if rpr is not None:
        shd = rpr.find(qn("w:shd"))
        if shd is not None:
            fill = (shd.get(qn("w:fill")) or "").upper()
            if fill and fill not in ("AUTO", "FFFFFF", "FFFFFFFF"):
                return True
    return False


def _extract_pdf_text(data: bytes) -> str:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    lines: list[str] = []
    for page in doc:
        highlight_rects = [
            annot.rect for annot in (page.annots() or []) if annot.type[1] == "Highlight"
        ]
        # some PDFs (e.g. exported from Word) bake highlights in as colored
        # vector rects drawn behind the text rather than real Highlight annots
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            if fill and _is_colorful(fill):
                highlight_rects.append(fitz.Rect(drawing["rect"]))
        # word-level granularity: get_text("dict") spans cover whole font runs,
        # which over-marks neighboring words as SELECTED when only one word in
        # the run is highlighted. words() gives per-word boxes instead.
        words = page.get_text("words")  # x0,y0,x1,y1,word,block_no,line_no,word_no
        grouped: dict[tuple[int, int], list] = {}
        for w in words:
            grouped.setdefault((w[5], w[6]), []).append(w)

        for key_words in grouped.values():
            key_words.sort(key=lambda w: w[7])
            parts = []
            for w in key_words:
                word_rect = fitz.Rect(w[:4])
                word = w[4]
                if _is_highlighted(word_rect, highlight_rects):
                    parts.append(f"[SELECTED: {word}]")
                else:
                    parts.append(word)
            line_text = " ".join(parts).strip()
            if line_text:
                # merge "[SELECTED: Yes] [SELECTED: □]" into "[SELECTED: Yes □]" —
                # checkbox glyph right after a highlighted word gets its own
                # redundant marker since they're separate "words" to PyMuPDF
                line_text = re.sub(
                    r"\[SELECTED: ([^\]]+)\] \[SELECTED: ([□▢☐])\]",
                    r"[SELECTED: \1 \2]",
                    line_text,
                )
                lines.append(line_text)
    return "\n".join(lines)


def _is_colorful(fill) -> bool:
    # skip white/black/gray fills (page background, table borders, headers) —
    # only treat saturated fills (yellow, green, cyan, etc.) as highlights
    r, g, b = fill
    return max(r, g, b) - min(r, g, b) >= 0.15


def _is_highlighted(word_rect, highlight_rects) -> bool:
    # require majority overlap, not just touching edges — highlight annot rects
    # are padded a few points beyond the marked text and can graze neighboring words
    word_area = word_rect.get_area()
    if word_area <= 0:
        return False
    for rect in highlight_rects:
        overlap = word_rect & rect
        if not overlap.is_empty and overlap.get_area() >= 0.5 * word_area:
            return True
    return False


# ---- XLSX extraction ----------------------------------------------------
# The VDD workbook is a grid, not prose: one question per row, with the question
# in the Parameter column and the reviewer's answer typed into the Response
# column. So there is no highlight pass here — unlike the DOCX and PDF paths,
# nothing about the answer is carried by formatting, and inspecting cell fills
# would only mistake header bands and banded table rows for answers.
#
# Output shape matches _extract_docx_text() exactly (one line per row, cells
# joined with " | "), so _mark_checked_boxes and everything downstream that walks
# lines works on this branch unchanged.
#
# Not extracted, with no signal that they were skipped: charts, images, text
# boxes and cell comments. None live in the cell grid, so openpyxl cannot see
# them on any code path.

_SHEET_HEADING = "=== Sheet: {title} ==="
# A stray formatted cell inflates a sheet's used range far past its real content
# (one sheet in the reference workbook reports max_row=1000 for 19 real rows), so
# cap total cells scanned rather than trusting the declared dimensions.
_MAX_XLSX_CELLS = 400_000


def _extract_xlsx_text(data: bytes) -> str:
    from openpyxl import load_workbook

    from app.services.form_export import cell_to_str

    wb = load_workbook(filename=io.BytesIO(data), read_only=False, data_only=True)
    try:
        blocks: list[str] = []
        budget = _MAX_XLSX_CELLS
        for sheet in wb.worksheets:
            # Hidden sheets in a VDD workbook are scoring rubrics, not the form.
            # They more than double the text, and one of them sorts ahead of the
            # real sheet — where its labels would win extract_canonical_fields'
            # first-match search.
            if sheet.sheet_state != "visible":
                continue
            text, budget = _xlsx_sheet_text(sheet, cell_to_str, budget)
            if text:
                blocks.append(_SHEET_HEADING.format(title=sheet.title) + "\n\n" + text)
            if budget <= 0:
                break
        return "\n\n".join(blocks)
    finally:
        wb.close()


def _xlsx_sheet_text(sheet, cell_to_str, budget: int) -> tuple[str, int]:
    covered = _merged_covered_cells(sheet)
    lines: list[str] = []
    for row in sheet.iter_rows():
        budget -= len(row)
        cells: list[str] = []
        for cell in row:
            # A merged range carries its value on the top-left cell only; the rest
            # read as None. Drop them rather than emitting empty filler, so a
            # Parameter merged across B:D reads "Parameter | Response", not
            # "Parameter |  |  | Response".
            if (cell.row, cell.column) in covered:
                continue
            cells.append(_sanitize_cell(cell_to_str(cell.value)))
        # Excel rows are as wide as the sheet's used range, not as wide as the
        # table, so without this every line trails a run of bare separators.
        # Interior blanks stay, to keep the columns aligned.
        while cells and not cells[-1]:
            cells.pop()
        if any(cells):
            lines.append(" | ".join(cells))
        if budget <= 0:
            break
    return "\n".join(lines), budget


def _merged_covered_cells(sheet) -> set[tuple[int, int]]:
    covered: set[tuple[int, int]] = set()
    for rng in sheet.merged_cells.ranges:
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    covered.add((r, c))
    return covered


def _sanitize_cell(value: str) -> str:
    # "|" is the column separator every line-oriented reader downstream relies on
    # (_TICK_RE, _is_boundary, _question_for), and a wrapped cell's newlines would
    # split one row across several lines. Collapse both.
    return " ".join(value.replace("|", "/").split())
