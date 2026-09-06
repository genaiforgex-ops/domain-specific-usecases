#!/usr/bin/env python3
"""Distill JFPSL legal template DOCX files into a prompt-ready standards markdown.

Reads DOCX from the configured templates directory (default: repo Templates/)
and writes backend/app/orchestrator/prompts/jfpsl_template_standards.md.

Usage:
    python backend/scripts/distill_template_playbook.py
    python backend/scripts/distill_template_playbook.py --templates-dir /path/to/Templates
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from docx import Document

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATES = REPO_ROOT / "Templates"
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "orchestrator"
    / "prompts"
    / "jfpsl_template_standards.md"
)

CLAUSE_KEYWORDS = {
    "liability": ["liability", "limitation of liability", "cap on liability"],
    "indemnity": ["indemnity", "indemnif", "hold harmless"],
    "termination": ["termination", "terminate", "term and termination"],
    "confidentiality": ["confidential", "non-disclosure", "nda"],
    "data_protection": ["personal data", "data protection", "dpdp", "privacy", "gdpr"],
    "governing_law": ["governing law", "jurisdiction", "dispute resolution", "arbitration"],
    "ip": ["intellectual property", " ip ", "copyright", "patent", "trademark"],
    "payment": ["payment", "fees", "invoice", "consideration"],
    "audit": ["audit", "inspect", "books and records"],
    "subcontracting": ["subcontract", "sub-contract", "assign", "assignment"],
}

TYPE_RULES: list[tuple[str, str]] = [
    ("nda", r"\bnda\b|mutual nda|non-?disclosure"),
    ("outsourcing", r"outsourcing"),
    ("sow", r"\bsow\b|statement of work"),
    ("deed_of_adherence", r"deed of adherence"),
    ("addendum", r"addendum"),
    ("intercompany", r"intercompany|inter-company|app hosting"),
    ("msa_gpa", r"\bmsa\b|service provider|general service provider|\bgpa\b|lsp"),
]


def classify(filename: str) -> str:
    name = filename.lower()
    for label, pattern in TYPE_RULES:
        if re.search(pattern, name):
            return label
    return "other"


def _is_heading(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 120:
        return False
    if re.match(r"^\d+(\.\d+)*[\.\)]?\s+\S", t):
        return True
    if t.isupper() and len(t.split()) <= 12:
        return True
    if re.match(r"^(article|schedule|annexure|exhibit)\s", t, re.I):
        return True
    return False


def _match_topics(text: str) -> set[str]:
    low = f" {text.lower()} "
    hits: set[str] = set()
    for topic, keys in CLAUSE_KEYWORDS.items():
        if any(k in low for k in keys):
            hits.add(topic)
    return hits


def extract_from_docx(path: Path) -> dict[str, list[str]]:
    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    by_topic: dict[str, list[str]] = defaultdict(list)
    current_heading = ""
    for para in paragraphs:
        if _is_heading(para):
            current_heading = para
            continue
        blob = f"{current_heading}\n{para}" if current_heading else para
        topics = _match_topics(blob)
        excerpt = para if len(para) <= 480 else para[:477] + "…"
        for topic in topics:
            if len(by_topic[topic]) < 2:
                label = f"[{path.name}] {excerpt}"
                if label not in by_topic[topic]:
                    by_topic[topic].append(label)
    return by_topic


def build_markdown(sources: dict[str, dict[str, list[str]]]) -> str:
    lines = [
        "# JFPSL Template Standards (distilled)",
        "",
        "Auto-generated from JFPSL legal template DOCX files. Use as internal",
        "standard-position guidance alongside Vertex RAG retrieval.",
        "",
    ]
    topic_titles = {
        "liability": "Limitation of Liability",
        "indemnity": "Indemnity",
        "termination": "Termination",
        "confidentiality": "Confidentiality / NDA",
        "data_protection": "Data Protection",
        "governing_law": "Governing Law & Disputes",
        "ip": "Intellectual Property",
        "payment": "Payment & Fees",
        "audit": "Audit & Inspection",
        "subcontracting": "Subcontracting & Assignment",
    }
    for agreement_type, topic_map in sorted(sources.items()):
        lines.append(f"## {agreement_type.replace('_', ' ').title()}")
        lines.append("")
        if not topic_map:
            lines.append("- _(No clause excerpts extracted — see source filename in corpus.)_")
            lines.append("")
            continue
        for topic, title in topic_titles.items():
            excerpts = topic_map.get(topic) or []
            if not excerpts:
                continue
            lines.append(f"### {title}")
            for ex in excerpts[:2]:
                lines.append(f"- {ex}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Distill JFPSL template DOCX into markdown.")
    parser.add_argument("--templates-dir", type=Path, default=DEFAULT_TEMPLATES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    templates_dir: Path = args.templates_dir
    if not templates_dir.is_dir():
        print(f"[error] templates dir not found: {templates_dir}", file=sys.stderr)
        return 1

    sources: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    files = sorted(templates_dir.glob("*.docx"))
    processed = 0
    for path in files:
        if path.stat().st_size == 0:
            print(f"[skip] empty file: {path.name}")
            continue
        agreement = classify(path.name)
        try:
            extracted = extract_from_docx(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] failed {path.name}: {exc}")
            continue
        for topic, excerpts in extracted.items():
            for ex in excerpts:
                if ex not in sources[agreement][topic]:
                    sources[agreement][topic].append(ex)
        processed += 1
        print(f"[ok]   {path.name} → {agreement} ({len(extracted)} topics)")

    md = build_markdown(sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"[done] wrote {args.output} ({processed} files, {len(md)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
