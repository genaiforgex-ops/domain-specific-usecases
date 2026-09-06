"""JFPSL legal-template RAG tool for JioLegal agents (Vertex AI RAG Engine)."""

from __future__ import annotations

import logging

from google.adk.tools import FunctionTool

from app.orchestrator import config as orch_config
from app.services.jfpsl_rag_service import search_jfpsl_corpus

logger = logging.getLogger("legalos.orchestrator")

_UNAVAILABLE = (
    "JFPSL legal-template search is currently unavailable. Answer from attached context "
    "and note that corpus lookup could not be performed."
)


def search_jfpsl_knowledge(query: str) -> str:
    """Search JFPSL legal templates via Google Vertex AI RAG Engine.

    Use this for questions about JFPSL contract templates, standard legal positions,
    policy clauses, MSA/NDA wording, compliance templates, and similar documents
    indexed in the Vertex RAG legal-templates corpus.

    Call this BEFORE web_search when the question is about JFPSL internal templates
    or standard legal language. Do NOT use for greetings, small talk, or when
    attached documents already contain the answer.
    After calling, synthesize an answer and cite the template sources returned.
    """
    if not orch_config.JFPSL_RAG_ENABLED:
        return _UNAVAILABLE

    q = (query or "").strip()
    if not q:
        return "Provide a search query about JFPSL legal templates or standard positions."

    try:
        from app.orchestrator.runtime import mark_corpus_result
        from app.services.jfpsl_rag_service import is_rag_insufficient

        result = search_jfpsl_corpus(q, max_results=orch_config.JFPSL_RAG_MAX_RESULTS)
        mark_corpus_result(had_hits=not is_rag_insufficient(result))
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_jfpsl_knowledge failed: %s", exc)
        from app.orchestrator.runtime import mark_corpus_result

        mark_corpus_result(had_hits=False)
        return _UNAVAILABLE


jfpsl_rag_tool = FunctionTool(search_jfpsl_knowledge)
