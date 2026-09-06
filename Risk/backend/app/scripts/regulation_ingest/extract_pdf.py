"""PyMuPDF-based raw block extraction for regulation source PDFs.

Produces page-tagged text blocks, one per paragraph-ish region as PyMuPDF
segments them. This is the first stage of the ingestion pipeline; output
feeds chunk_clauses.py, which groups blocks into numbered-paragraph clauses.

Kept separate from app.services.document_extract — that module extracts
*vendor-submitted* documents for checkbox-highlight detection in M3 forms, a
different concern from parsing a regulator's own gazetted PDF for citation.

Usage:
    python -m app.scripts.regulation_ingest.extract_pdf <pdf_path> [-o out.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

_NOISE_PATTERNS = (
    re.compile(r"^\d{1,4}$"),  # bare page number
    re.compile(r"^RESERVE BANK OF INDIA$", re.IGNORECASE),
    re.compile(r"^SECURITIES AND EXCHANGE BOARD OF INDIA$", re.IGNORECASE),
    re.compile(r"^MASTER CIRCULAR$", re.IGNORECASE),
)


def extract_blocks(pdf_path: str) -> list[dict]:
    """Return ordered [{page_no, text}, ...] for every non-noise text block
    in the PDF, page_no is 1-indexed to match how the documents themselves
    print page numbers."""
    doc = fitz.open(pdf_path)
    try:
        return _extract_blocks_from_doc(doc)
    finally:
        doc.close()


def extract_blocks_from_bytes(data: bytes) -> list[dict]:
    """Same as extract_blocks, but for PDF bytes already in memory (e.g. an
    uploaded file) instead of a path on disk — avoids temp-file plumbing for
    the Library upload flow."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return _extract_blocks_from_doc(doc)
    finally:
        doc.close()


def _extract_blocks_from_doc(doc) -> list[dict]:
    blocks: list[dict] = []
    for page_index, page in enumerate(doc, start=1):
        for b in page.get_text("blocks"):
            # b = (x0, y0, x1, y1, text, block_no, block_type)
            text = " ".join(b[4].split())
            if not text or _is_noise(text):
                continue
            blocks.append({"page_no": page_index, "text": text})
    return blocks


def _is_noise(text: str) -> bool:
    return any(p.match(text) for p in _NOISE_PATTERNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf_path")
    parser.add_argument("-o", "--out", help="write JSON blocks here instead of stdout")
    args = parser.parse_args()

    blocks = extract_blocks(args.pdf_path)
    payload = json.dumps(blocks, indent=2)
    if args.out:
        Path(args.out).write_text(payload)
        print(f"Wrote {len(blocks)} blocks to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
