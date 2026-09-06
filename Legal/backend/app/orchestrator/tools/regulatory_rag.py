"""Regulatory law RAG tool — statutes, master directions and circulars.

Distinct from `jfpsl_rag`: that corpus holds JFPSL's own templates and executed
contracts, this one holds the law itself, chunked clause by clause so answers can
cite provisions ("Para 5.3") rather than page numbers.
"""

from __future__ import annotations

import logging

from google.adk.tools import FunctionTool

from app.orchestrator import config as orch_config
from app.services.regulatory_rag_service import search_regulatory_corpus

logger = logging.getLogger("legalos.orchestrator")

_UNAVAILABLE = (
    "Regulatory corpus search is currently unavailable. Use web_search against "
    "official regulator sites (rbi.org.in, sebi.gov.in, irdai.gov.in, npci.org.in, "
    "meity.gov.in) and flag that primary-source verification is pending."
)


def search_regulatory_knowledge(query: str) -> str:
    """Search Indian financial-services law for the exact provision that applies.

    Covers RBI Master Directions and Directions (digital lending, KYC, PPI, payment
    aggregators, NBFC fair practices), SEBI regulations and master circulars, IRDAI
    regulations, NPCI circulars, MeitY/CERT-In rules, and the underlying bare Acts
    (DPDP, PMLA, IT Act, Contract Act, Consumer Protection, PSS Act, Banking
    Regulation, RBI Act, SEBI Act, Depositories, Insurance).

    Call this FIRST for any question about what the law, a regulator, or a
    compliance rule requires — before web_search, and before search_jfpsl_knowledge
    unless the question is specifically about JFPSL's own templates or positions.
    Superseded provisions are excluded automatically unless the question asks about
    historical law.

    Returns numbered clause excerpts with the issuer, provision label and effective
    date. Cite them by bracket number and name the provision; never invent a clause
    number, circular number or date.
    """
    if not orch_config.REGULATORY_RAG_ENABLED:
        return _UNAVAILABLE

    q = (query or "").strip()
    if not q:
        return "Provide a question about Indian financial-services law or regulation."

    try:
        from app.orchestrator.runtime import mark_corpus_result
        from app.services.regulatory_rag_service import is_corpus_insufficient

        result = search_regulatory_corpus(
            q, max_results=orch_config.REGULATORY_RAG_MAX_RESULTS
        )
        mark_corpus_result(had_hits=not is_corpus_insufficient(result))
        # Surface thin / missing corpus for Research Thoughts.
        if is_corpus_insufficient(result):
            from app.orchestrator.runtime import current_runtime

            rt = current_runtime()
            if rt is not None:
                rt.notes.append(
                    "Regulatory corpus returned no usable clauses for this query "
                    "(ingest may be incomplete or stale)."
                )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_regulatory_knowledge failed: %s", exc)
        from app.orchestrator.runtime import mark_corpus_result

        mark_corpus_result(had_hits=False)
        return _UNAVAILABLE


regulatory_rag_tool = FunctionTool(search_regulatory_knowledge)
