"""Extract plain text from uploaded legal documents."""

from __future__ import annotations

import io
from pathlib import Path


class DocumentParseError(Exception):
    pass


def parse_document(data: bytes, filename: str, mime_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()
    if mime_type:
        if "pdf" in mime_type:
            ext = ".pdf"
        elif "word" in mime_type or "docx" in mime_type:
            ext = ".docx"

    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace").strip()
    if ext == ".pdf":
        return _parse_pdf(data)
    if ext in (".docx", ".doc"):
        return _parse_docx(data)
    # Fallback: try UTF-8 text
    try:
        text = data.decode("utf-8").strip()
        if text:
            return text
    except UnicodeDecodeError:
        pass
    raise DocumentParseError(f"Unsupported file type: {ext or mime_type}")


def _parse_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise DocumentParseError("pypdf not installed") from e
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DocumentParseError("Encrypted PDFs are not supported")
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    result = "\n\n".join(parts).strip()
    if not result:
        raise DocumentParseError("No text could be extracted from PDF")
    return result


def accepted_paragraph_text(paragraph) -> str:
    """Paragraph text with tracked changes accepted.

    Walks the paragraph in document order: text inside tracked insertions
    (<w:ins>) is kept, tracked deletions (stored as <w:delText>) are skipped,
    and tabs/breaks are rendered like python-docx's ``run.text``. This yields
    the "all changes accepted" (final) text. ``paragraph.text`` alone would miss
    runs nested in <w:ins>; for a document with no tracked changes this returns
    exactly the same string as ``paragraph.text``.
    """
    from docx.oxml.ns import qn

    t, tab, br, cr = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
    out: list[str] = []
    for node in paragraph._p.iter():
        if node.tag == t:
            out.append(node.text or "")
        elif node.tag == tab:
            out.append("\t")
        elif node.tag in (br, cr):
            out.append("\n")
    return "".join(out)


def _parse_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise DocumentParseError("python-docx not installed") from e
    doc = Document(io.BytesIO(data))
    parts = [t for p in doc.paragraphs if (t := accepted_paragraph_text(p)).strip()]
    result = "\n\n".join(parts).strip()
    if not result:
        raise DocumentParseError("No text could be extracted from DOCX")
    return result


def render_text_to_pdf(text: str, title: str | None = None) -> bytes | None:
    """Render plain text into a clean, paginated PDF. Returns None if reportlab
    is unavailable so callers can fall back to a text version."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return None

    from xml.sax.saxutils import escape

    from app.services.markdown_tables import iter_content_segments, normalize_markdown_tables

    text = normalize_markdown_tables(text)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
        title=title or "Document",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "LegalTitle",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=13,
        leading=18,
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "LegalBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14.5,
        alignment=TA_LEFT,
        spaceAfter=7,
        firstLineIndent=0,
    )
    cell_style = ParagraphStyle(
        "LegalTableCell",
        parent=body,
        fontSize=9,
        leading=12,
        spaceAfter=0,
    )
    flow = []
    if title:
        flow.append(Paragraph(escape(title), heading))

    for kind, payload in iter_content_segments(text):
        if kind == "table":
            rows = payload  # type: ignore[assignment]
            assert isinstance(rows, list)
            table_data = [
                [Paragraph(escape(cell), cell_style) for cell in row] for row in rows
            ]
            tbl = Table(table_data, hAlign="LEFT")
            tbl.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.94, 0.97)),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.7, 0.72, 0.78)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            flow.append(tbl)
            flow.append(Spacer(1, 8))
            continue

        assert isinstance(payload, str)
        for block in payload.split("\n"):
            if block.strip():
                flow.append(Paragraph(escape(block), body))
            else:
                flow.append(Spacer(1, 6))

    if not flow:
        flow.append(Paragraph("(empty document)", body))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Times-Roman", 8)
        canvas.setFillColorRGB(0.45, 0.49, 0.57)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_text_to_docx(text: str, title: str | None = None) -> bytes | None:
    """Render plain text into a DOCX document, preserving an editable format.

    GitHub-flavored Markdown tables are converted to real Word tables so columns
    stay aligned after Ask AI to Edit.
    """
    try:
        from docx import Document
        from docx.shared import Inches, Pt
    except ImportError:
        return None

    from app.services.markdown_tables import iter_content_segments, normalize_markdown_tables

    text = normalize_markdown_tables(text)
    buffer = io.BytesIO()
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)

    if title:
        heading = doc.add_paragraph()
        run = heading.add_run(title)
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = Pt(13)

    for kind, payload in iter_content_segments(text):
        if kind == "table":
            rows = payload
            assert isinstance(rows, list) and rows
            cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            _populate_word_table(table, rows)
            doc.add_paragraph()
            continue

        assert isinstance(payload, str)
        for block in payload.split("\n"):
            if block.strip():
                para = doc.add_paragraph(block)
                para.paragraph_format.space_after = Pt(6)
                para.paragraph_format.line_spacing = 1.15
            else:
                doc.add_paragraph()

    doc.save(buffer)
    return buffer.getvalue()


def content_has_markdown_table(text: str) -> bool:
    """True when ``text`` contains at least one GFM table (re-export)."""
    from app.services.markdown_tables import content_has_markdown_table as _has

    return _has(text)


def insert_content_after_paragraph(ref_para, content: str):
    """Insert prose and/or real Word tables after ``ref_para``.

    GFM tables in ``content`` become ``w:tbl`` elements; other lines become
    paragraphs. Returns the last inserted paragraph (or ``ref_para`` if only
    tables were inserted / content empty).
    """
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    from app.services.markdown_tables import iter_content_segments, normalize_markdown_tables

    content = (content or "").strip()
    if not content:
        return ref_para

    doc = ref_para.part.document
    anchor = ref_para._p
    last_para = ref_para

    for kind, payload in iter_content_segments(normalize_markdown_tables(content)):
        if kind == "table":
            rows = payload
            assert isinstance(rows, list) and rows
            cols = max(len(r) for r in rows)
            # add_table appends at body end; relocate after the current anchor.
            table = doc.add_table(rows=len(rows), cols=cols)
            _populate_word_table(table, rows)
            tbl = table._tbl
            tbl.getparent().remove(tbl)
            anchor.addnext(tbl)
            anchor = tbl
            continue

        assert isinstance(payload, str)
        for block in payload.split("\n"):
            if not block.strip() and not payload.strip():
                continue
            new_p = OxmlElement("w:p")
            anchor.addnext(new_p)
            new_para = Paragraph(new_p, ref_para._parent)
            if ref_para.style:
                try:
                    new_para.style = ref_para.style
                except (AttributeError, KeyError, ValueError):
                    pass
            if block.strip():
                if ref_para.runs:
                    new_run = new_para.add_run(block)
                    src = ref_para.runs[0]
                    new_run.bold = src.bold
                    new_run.italic = src.italic
                    new_run.underline = src.underline
                else:
                    new_para.text = block
            anchor = new_p
            last_para = new_para

    return last_para


def replace_paragraph_with_content(para, content: str) -> bool:
    """Replace a paragraph with segmented content (text + real Word tables).

    The original paragraph becomes the first text line (or is cleared if content
    starts with a table). Subsequent segments are inserted after it.
    """
    from app.services.markdown_tables import iter_content_segments, normalize_markdown_tables

    content = (content or "").strip()
    segments = list(iter_content_segments(normalize_markdown_tables(content)))
    if not segments:
        _set_paragraph_runs_text(para, "")
        return True

    first_kind, first_payload = segments[0]
    remainder: list[str] = []

    if first_kind == "text":
        assert isinstance(first_payload, str)
        lines = first_payload.split("\n")
        _set_paragraph_runs_text(para, lines[0] if lines else "")
        if len(lines) > 1:
            remainder.append("\n".join(lines[1:]))
        for kind, payload in segments[1:]:
            if kind == "table":
                assert isinstance(payload, list)
                remainder.append(_rows_to_gfm(payload))
            else:
                assert isinstance(payload, str)
                remainder.append(payload)
    else:
        _set_paragraph_runs_text(para, "")
        for kind, payload in segments:
            if kind == "table":
                assert isinstance(payload, list)
                remainder.append(_rows_to_gfm(payload))
            else:
                assert isinstance(payload, str)
                remainder.append(payload)

    if remainder:
        insert_content_after_paragraph(para, "\n\n".join(remainder))
    return True


def _rows_to_gfm(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    def fmt(r: list[str]) -> str:
        cells = list(r) + [""] * (cols - len(r))
        return "| " + " | ".join(cells) + " |"

    header = fmt(rows[0])
    sep = "| " + " | ".join("---" for _ in range(cols)) + " |"
    body = [fmt(r) for r in rows[1:]]
    return "\n".join([header, sep, *body])


def _set_paragraph_runs_text(para, new_text: str) -> None:
    if not para.runs:
        para.text = new_text
        return
    first = para.runs[0]
    for run in para.runs[1:]:
        run.text = ""
    first.text = new_text


def _populate_word_table(table, rows: list[list[str]]) -> None:
    """Fill a python-docx Table with GFM-derived rows (header bold + shaded)."""
    from docx.shared import Pt

    cols = max(len(r) for r in rows) if rows else 0
    try:
        table.style = "Table Grid"
    except (AttributeError, KeyError, ValueError):
        pass
    for r_idx, row in enumerate(rows):
        for c_idx in range(cols):
            cell = table.rows[r_idx].cells[c_idx]
            cell.text = row[c_idx] if c_idx < len(row) else ""
            for cell_para in cell.paragraphs:
                for run in cell_para.runs:
                    run.font.name = "Times New Roman"
                    run.font.size = Pt(10)
                    if r_idx == 0:
                        run.bold = True
            if r_idx == 0:
                _set_cell_shading(cell, "EEF1F8")


def _set_cell_shading(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)
