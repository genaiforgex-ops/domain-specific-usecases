"""Group page-tagged text blocks (from extract_pdf.py) into numbered-paragraph
clauses with a stable, collision-free clause_ref.

RBI's two outsourcing directions and SEBI's master circular all number
paragraphs (1., 2., 2.1, 96-97...) but restart that numbering inside
chapters/annexures — RBI Chapter III para "15" and Chapter IV para "15"
don't exist simultaneously in these specific docs, but SEBI's Annexure A and
Annexure H both have a "1." Tracking the most recent chapter/section/annexure
heading as a running "context" label and folding it into clause_ref avoids
that collision without needing per-document special-casing.

This is a heuristic, not a legal-citation parser: headings are detected by a
few generic regexes (Chapter/Roman-numeral section/Annexure letter), and any
block that isn't itself a heading or a new numbered paragraph is folded into
the paragraph currently being accumulated. Good enough to get verbatim text
+ the page it started on for every paragraph; not guaranteed to reproduce a
perfect legal cross-reference for every edge case (e.g. text before the
first numbered paragraph in a document, such as the enacting preamble, has
no number to key off and is dropped — it's boilerplate, not outsourcing
substance).
"""
import re

_TOP_LEVEL_PARA = re.compile(r"^\(?(\d+(?:\.\d+){0,2})\)?[.:]\s+\S")
_CHAPTER_HEADER = re.compile(r"^Chapter\s+([IVXLCDM]+)\b", re.IGNORECASE)
_ROMAN_SECTION_HEADER = re.compile(r"^([IVXLCDM]+)\.\s+[A-Z]{3,}")
_ANNEXURE_HEADER = re.compile(r"^ANNEXURE\s+([A-Z])\b", re.IGNORECASE)


def detect_context(text: str) -> str | None:
    """Return a short context label if `text` is a heading that starts a new
    chapter/section/annexure, else None (not a heading)."""
    m = _ANNEXURE_HEADER.match(text)
    if m:
        return f"Anx{m.group(1).upper()}"
    m = _CHAPTER_HEADER.match(text)
    if m:
        return f"Ch{m.group(1).upper()}"
    m = _ROMAN_SECTION_HEADER.match(text)
    if m:
        return f"S{m.group(1).upper()}"
    return None


def chunk_paragraphs(blocks: list[dict]) -> list[dict]:
    """Group blocks into [{context, para_no, page_no, text}, ...].

    `page_no` is where the paragraph *starts*; a paragraph spanning a page
    break still carries its starting page (good enough granularity for
    citation — "Para 58, p.12" doesn't need to also say "...continues to
    p.13"). `context` disambiguates paragraph numbers that repeat across
    chapters/annexures (see module docstring).
    """
    chunks: list[dict] = []
    current: dict | None = None
    context = "Body"

    for block in blocks:
        text = block["text"]
        ctx = detect_context(text)
        if ctx:
            context = ctx
            continue  # heading itself isn't evidence text, just sets context

        m = _TOP_LEVEL_PARA.match(text)
        if m:
            if current:
                chunks.append(current)
            current = {
                "context": context,
                "para_no": m.group(1),
                "page_no": block["page_no"],
                "text": text,
            }
        elif current:
            current["text"] += "\n" + text
        # else: text before the first numbered paragraph (preamble/title) —
        # not evidence-worthy, dropped.

    if current:
        chunks.append(current)
    return chunks


def build_clause_ref(doc_prefix: str, chunk: dict) -> str:
    """e.g. build_clause_ref("RBI-NBFC-2025", {"context": "ChIII", "para_no": "15"})
    -> "RBI-NBFC-2025-ChIII-P15" """
    return f"{doc_prefix}-{chunk['context']}-P{chunk['para_no']}"


_PROHIBITED_KEYWORDS = (
    "shall not be outsourced", "shall not outsource", "not be outsourced",
    "core management function", "shall not", "prohibited",
)
_IT_KEYWORDS = (
    "it service", "cloud computing", "data centre", "data center",
    "software", "cyber", "information technology", "data security",
    "encryption", "saas", "cloud service",
)
_FINANCIAL_KEYWORDS = (
    "financial service", "kyc", "loan", "deposit", "credit card",
    "nbfc", "investment advice", "investment advisory", "advisory client",
)


def derive_tags(text: str) -> str:
    """Cheap keyword-based tag for the same financial/it/prohibited/general
    buckets the M1 classification labels use — lets clause_retrieval.py
    cheaply boost clauses whose tag matches the input's likely label without
    needing an LLM call per clause."""
    lowered = text.lower()
    if any(k in lowered for k in _PROHIBITED_KEYWORDS):
        return "prohibited"
    if any(k in lowered for k in _IT_KEYWORDS):
        return "it"
    if any(k in lowered for k in _FINANCIAL_KEYWORDS):
        return "financial"
    return "general"
