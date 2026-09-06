"""Build standard-position context for UC-01 contract review prompts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.config import settings
from app.orchestrator.prompts.loaders import load_jfpsl_template_standards
from app.services.jfpsl_rag_service import is_rag_insufficient, search_jfpsl_corpus


def format_playbook(playbook: Sequence[Any]) -> str:
    if not playbook:
        return "(No standard-position entries provided for this arrangement type.)"
    lines: list[str] = []
    for p in playbook:
        clause_type = getattr(p, "clause_type", "general")
        position = getattr(p, "standard_position", "")
        notes = getattr(p, "notes", None)
        lines.append(f"- [{clause_type}] {position}" + (f" (note: {notes})" if notes else ""))
    return "\n".join(lines)


def build_review_context(
    contract_type: str,
    playbook: Sequence[Any],
    *,
    rag_max_results: int | None = None,
) -> str:
    """Distilled standards + Vertex RAG excerpts + DB playbook for review agents."""
    max_results = rag_max_results or settings.orch_jfpsl_rag_max_results
    rag_query = (
        f"{contract_type} JFPSL standard positions liability indemnity termination "
        "confidentiality data protection governing law intellectual property payment"
    )
    rag_context = search_jfpsl_corpus(rag_query, max_results=max_results)
    if is_rag_insufficient(rag_context):
        rag_block = f"(Vertex RAG: no template hits — {rag_context})"
    else:
        rag_block = rag_context

    standards = load_jfpsl_template_standards()
    playbook_block = format_playbook(playbook)

    return (
        f"ARRANGEMENT TYPE: {contract_type}\n\n"
        f"JFPSL TEMPLATE STANDARDS (distilled from approved templates):\n{standards}\n\n"
        f"JFPSL TEMPLATE RAG EXCERPTS (Vertex AI RAG Engine):\n{rag_block}\n\n"
        f"OUR STANDARD POSITION (playbook database):\n{playbook_block}"
    )
