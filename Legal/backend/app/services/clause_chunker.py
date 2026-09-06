"""Clause-aware chunking for regulatory text.

Legal text has structure a character-budget chunker throws away: a chunk that
splits Section 6(2)(b) mid-sentence can never be cited as "Section 6(2)(b)".
This module splits on the *legal hierarchy* instead, so every chunk carries the
provision label the citation is built from.

Pure functions — no DB, no LLM, no network. `extract_pages` deliberately does not
reuse `document_parser.parse_document`, because that flattens a PDF into one
string and page numbers are needed for the Evidence-panel jump.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ~4 chars per token is close enough for a chunk budget.
_CHARS_PER_TOKEN = 4
MIN_TOKENS = 60
TARGET_TOKENS = 900
MAX_TOKENS = 1200
_FALLBACK_CHUNK_CHARS = 1800

# A heading line is short and not a full sentence; used to attach parent context.
_MAX_HEADING_CHARS = 160


class ClauseChunkError(Exception):
    """Raised when no usable text can be extracted."""


@dataclass(frozen=True)
class ClauseChunk:
    """One leaf provision, ready to embed and cite."""

    text: str
    page: int
    ordinal: int
    section_label: str | None = None
    parent_heading: str | None = None

    @property
    def token_count(self) -> int:
        return max(1, len(self.text) // _CHARS_PER_TOKEN)


# ── Provision-header patterns, keyed by manifest doc_type ────────────────────
# Each pattern must expose a `num` group; the label prefix names the provision
# the way the issuer does, which is what ends up in the cite chip.
_PATTERNS: dict[str, tuple[str, re.Pattern[str]]] = {
    # Bare Acts: "6. Definitions" / "43A. Compensation ..."
    "bare_act": ("Section", re.compile(r"^\s*(?P<num>\d+[A-Z]{0,2})\.\s+(?=\S)")),
    # RBI Master Directions / Directions: "5.3 Cooling-off period"
    "master_direction": ("Para", re.compile(r"^\s*(?P<num>\d+(?:\.\d+){0,3})\.?\s+(?=\S)")),
    "directions": ("Para", re.compile(r"^\s*(?P<num>\d+(?:\.\d+){0,3})\.?\s+(?=\S)")),
    # SEBI master circulars / circulars: "4.2 Disclosure"
    "master_circular": ("Clause", re.compile(r"^\s*(?P<num>\d+(?:\.\d+){0,3})\.?\s+(?=\S)")),
    "circular": ("Clause", re.compile(r"^\s*(?P<num>\d+(?:\.\d+){0,3})\.?\s+(?=\S)")),
    # Statutory rules: "Rule 7." or bare "7."
    "rules": ("Rule", re.compile(r"^\s*(?:Rule\s+)?(?P<num>\d+[A-Z]{0,2})\.?\s+(?=\S)")),
    # SEBI/IRDAI regulations: "Regulation 12." or bare "12."
    "regulation": (
        "Regulation",
        re.compile(r"^\s*(?:Regulation\s+)?(?P<num>\d+[A-Z]{0,2})\.?\s+(?=\S)"),
    ),
    "scheme": ("Clause", re.compile(r"^\s*(?:Clause|Para)?\s*(?P<num>\d+(?:\.\d+){0,2})\.?\s+(?=\S)")),
    "charter": ("Clause", re.compile(r"^\s*(?:Clause|Para)?\s*(?P<num>\d+(?:\.\d+){0,2})\.?\s+(?=\S)")),
}
_DEFAULT_PATTERN = ("Para", re.compile(r"^\s*(?P<num>\d+(?:\.\d+){0,3})\.?\s+(?=\S)"))

# Sub-clause openers used to split an over-long provision without cutting a
# numbered item in half: "(a)", "(2)", "(iv)".
_SUBCLAUSE_RE = re.compile(r"^\s*\((?P<num>[a-z]{1,3}|\d{1,2}|[ivxl]{1,5})\)\s+", re.IGNORECASE)

# Page furniture that would otherwise pollute a clause chunk.
_NOISE_RE = re.compile(
    r"^\s*(?:page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|[-–—\s]*\d+[-–—\s]*)\s*$",
    re.IGNORECASE,
)


def _pattern_for(doc_type: str) -> tuple[str, re.Pattern[str]]:
    return _PATTERNS.get((doc_type or "").strip().lower(), _DEFAULT_PATTERN)


def _clean_line(line: str) -> str:
    return re.sub(r"[ \t]+", " ", line.replace("\xa0", " ")).rstrip()


def _looks_like_heading(line: str) -> bool:
    """A short, sentence-less line — a chapter/part title worth carrying down."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return False
    if stripped.endswith((".", ";", ":")) and not stripped.isupper():
        return False
    words = stripped.split()
    if len(words) > 14:
        return False
    return stripped.isupper() or bool(
        re.match(r"^(?:CHAPTER|PART|SCHEDULE|ANNEX|SECTION)\b", stripped, re.IGNORECASE)
    )


# ── Text extraction (page-preserving) ───────────────────────────────────────
def extract_pages(data: bytes, filename: str, mime_type: str | None = None) -> list[str]:
    """Document text as one string per page (1-indexed by list position)."""
    ext = Path(filename or "").suffix.lower()
    if mime_type:
        if "pdf" in mime_type:
            ext = ".pdf"
        elif "word" in mime_type or "docx" in mime_type:
            ext = ".docx"

    if ext == ".pdf":
        pages = _pdf_pages(data)
    elif ext in (".docx", ".doc"):
        from app.services.document_parser import _parse_docx

        pages = [_parse_docx(data)]
    elif ext in (".html", ".htm"):
        pages = [_html_text(data)]
    else:
        pages = [data.decode("utf-8", errors="replace")]

    pages = [p for p in (p.strip() for p in pages) if p]
    if not pages:
        raise ClauseChunkError(f"No text could be extracted from {filename!r}")
    return pages


def _pdf_pages(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - pypdf is pinned
        raise ClauseChunkError("pypdf not installed") from exc

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ClauseChunkError("Encrypted PDFs are not supported")
    return [(page.extract_text() or "") for page in reader.pages]


def _html_text(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text("\n")


# ── Clause-aware chunking ───────────────────────────────────────────────────
@dataclass
class _Provision:
    label: str | None
    heading: str | None
    lines: list[str]
    page: int

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def chunk_clauses(pages: list[str], *, doc_type: str, doc_id: str = "") -> list[ClauseChunk]:
    """Split page text into one chunk per leaf provision.

    Provision headers are detected per `doc_type`; the section heading stays with
    its body; over-long provisions are split on sub-clause boundaries with the
    parent label and heading repeated so each child is still citable.
    """
    label_prefix, header_re = _pattern_for(doc_type)
    provisions: list[_Provision] = []
    current: _Provision | None = None
    heading: str | None = None

    for page_no, page_text in enumerate(pages, start=1):
        for raw_line in (page_text or "").splitlines():
            line = _clean_line(raw_line)
            if not line.strip() or _NOISE_RE.match(line):
                continue

            match = header_re.match(line)
            if match:
                current = _Provision(
                    label=f"{label_prefix} {match.group('num')}",
                    heading=heading,
                    lines=[line.strip()],
                    page=page_no,
                )
                provisions.append(current)
                continue

            if _looks_like_heading(line):
                heading = line.strip()
                # A heading closes the previous provision rather than joining it.
                current = None
                continue

            if current is None:
                # Preamble before the first numbered provision.
                current = _Provision(label=None, heading=heading, lines=[], page=page_no)
                provisions.append(current)
            current.lines.append(line.strip())

    chunks = _provisions_to_chunks(provisions)
    if not chunks:
        logger.info(
            "No provision structure found in %s (%s) — falling back to paragraph packing",
            doc_id or "document",
            doc_type,
        )
        chunks = _fallback_chunks(pages)
    return chunks


def _provisions_to_chunks(provisions: list[_Provision]) -> list[ClauseChunk]:
    """One chunk per labelled provision; oversized ones split on sub-clauses.

    A labelled provision is never merged into another, however short it is — a
    one-line commencement clause still has to be citable as its own paragraph.
    Unlabelled preamble is kept only when it carries enough text to be useful.
    """
    if not any(p.label and p.text for p in provisions):
        return []

    out: list[ClauseChunk] = []
    for prov in provisions:
        if not prov.text:
            continue
        if prov.label is None:
            # Preamble/applicability text ahead of the first numbered provision.
            if not out and _tokens(prov.text) >= MIN_TOKENS:
                out.extend(_emit(prov, len(out)))
            continue
        out.extend(_emit(prov, len(out)))
    return out


def _emit(prov: _Provision, start_ordinal: int) -> list[ClauseChunk]:
    text = prov.text
    if _tokens(text) <= MAX_TOKENS:
        return [
            ClauseChunk(
                text=text,
                page=prov.page,
                ordinal=start_ordinal,
                section_label=prov.label,
                parent_heading=prov.heading,
            )
        ]
    return _split_oversized(prov, start_ordinal)


def _split_oversized(prov: _Provision, start_ordinal: int) -> list[ClauseChunk]:
    """Split on sub-clause boundaries, repeating the parent header in each child."""
    lines = prov.lines
    header_line = lines[0] if lines else ""
    groups: list[list[str]] = []
    buf: list[str] = []

    for line in lines[1:]:
        starts_subclause = bool(_SUBCLAUSE_RE.match(line))
        if starts_subclause and buf and _tokens("\n".join(buf)) >= TARGET_TOKENS // 2:
            groups.append(buf)
            buf = [line]
            continue
        buf.append(line)
        if _tokens("\n".join(buf)) >= TARGET_TOKENS and not starts_subclause:
            groups.append(buf)
            buf = []
    if buf:
        groups.append(buf)
    if not groups:
        groups = [lines[1:]]

    chunks: list[ClauseChunk] = []
    total = len(groups)
    for idx, group in enumerate(groups):
        # Repeat the parent provision header so every child stays citable.
        body = "\n".join([header_line, *group]).strip()
        label = prov.label if total == 1 else f"{prov.label} ({idx + 1}/{total})"
        chunks.append(
            ClauseChunk(
                text=body,
                page=prov.page,
                ordinal=start_ordinal + idx,
                section_label=label,
                parent_heading=prov.heading,
            )
        )
    return chunks


def _fallback_chunks(pages: list[str]) -> list[ClauseChunk]:
    """Paragraph packing for documents with no detectable provision numbering."""
    out: list[ClauseChunk] = []
    for page_no, page_text in enumerate(pages, start=1):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page_text or "") if p.strip()]
        if not paragraphs:
            continue
        buf = ""
        for para in paragraphs:
            if buf and len(buf) + len(para) + 2 > _FALLBACK_CHUNK_CHARS:
                out.append(ClauseChunk(text=buf, page=page_no, ordinal=len(out)))
                buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf:
            out.append(ClauseChunk(text=buf, page=page_no, ordinal=len(out)))
    return out


def _tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def chunk_key(doc_id: str, chunk: ClauseChunk) -> str:
    """Stable, human-readable chunk id, e.g. `LEND-DLD-2025:para-5-3`."""
    if chunk.section_label:
        slug = re.sub(r"[^a-z0-9]+", "-", chunk.section_label.lower()).strip("-")
    else:
        slug = f"chunk-{chunk.ordinal}"
    return f"{doc_id}:{slug}"[:160]
