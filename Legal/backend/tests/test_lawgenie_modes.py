"""Unit tests for research fan-out lanes, groundedness helpers, and mode directives.

These always run in CI (no embedding / live LLM). Heavier RAG eval stays behind
``RUN_RAG_EVAL=1``.
"""

from __future__ import annotations

from app.orchestrator.pipeline import _MODE_DIRECTIVES
from app.orchestrator.research_fanout import LaneResult, plan_detail
from app.services.regulatory_router import RouteDecision


def test_mode_directives_cover_review_research_draft():
    assert "REVIEW" in _MODE_DIRECTIVES["review"]
    assert "RESEARCH" in _MODE_DIRECTIVES["research"]
    assert "DRAFT" in _MODE_DIRECTIVES["draft"]
    assert "[[PLACEHOLDER:" in _MODE_DIRECTIVES["draft"]
    assert "search_jfpsl_knowledge" in _MODE_DIRECTIVES["draft"]
    assert "synthesize" in _MODE_DIRECTIVES["research_with_preretrieved"].lower() or (
        "Pre-retrieved" in _MODE_DIRECTIVES["research_with_preretrieved"]
    )


def test_plan_detail_marks_web_search_disabled():
    route = RouteDecision(
        domains=["lending_credit"],
        site_hosts=["rbi.org.in"],
        use_regulatory=True,
        include_superseded=False,
        needs_web=True,
        matched_tags=["digital_lending"],
    )
    lanes = [
        LaneResult(name="open_web", label="Open web", error="web search disabled"),
    ]
    detail = plan_detail("cooling-off period", route, lanes)
    assert "web search disabled" in detail


def test_groundedness_mark_unsupported_rewrites_citation():
    from app.orchestrator.groundedness import mark_unsupported

    text = "The cooling-off period is 3 days [1]."
    out = mark_unsupported(text, [1])
    assert "[unverified]" in out


def test_web_allowed_draft_blocks():
    from app.orchestrator.runtime import request_runtime, web_allowed_for_mode

    with request_runtime(1, "legal_user", mode="draft"):
        ok, msg = web_allowed_for_mode()
        assert ok is False
        assert "DRAFT" in msg


def test_web_allowed_review_requires_corpus_first():
    from app.orchestrator.runtime import (
        mark_corpus_result,
        request_runtime,
        web_allowed_for_mode,
    )

    with request_runtime(1, "legal_user", mode="review"):
        ok, _ = web_allowed_for_mode()
        assert ok is False
        mark_corpus_result(had_hits=False)
        ok2, _ = web_allowed_for_mode()
        assert ok2 is True
