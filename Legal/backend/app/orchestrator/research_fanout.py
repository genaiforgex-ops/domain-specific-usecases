"""Parallel retrieval for Research mode.

Today's research mode is a prompt directive: one agent issues tool calls one after
another, so covering the corpus plus three regulator sites costs four serial
round-trips. This module fetches those lanes concurrently and hands the agent the
retrieved text up front, so it spends its turn synthesising rather than fetching.

Two deliberate constraints:

* **Fetch concurrently, record sequentially.** Lanes only *fetch*; the parent
  coroutine records their sources in a fixed lane order afterwards. Citation
  numbers are absolute across a turn, so recording from whichever lane happens to
  finish first would renumber citations non-deterministically.
* **Nothing here is allowed to fail a turn.** Every lane is wrapped in a timeout
  and a catch; a dead lane is reported and dropped.

JFPSL templates are deliberately *not* a lane — `search_jfpsl_knowledge` records
and formats in one step, and the agent can still call it as a tool. Splitting that
service apart to gain one parallel slot is not worth the churn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import anyio

from app.orchestrator import config as orch_config
from app.services.regulatory_router import RouteDecision

logger = logging.getLogger("legalos.orchestrator")

# Regulator sites are the whole point of the site-scoped lane; more than a handful
# of `site:` terms in one query starts degrading result quality.
_MAX_SITE_HOSTS = 4
_MAX_CONCURRENT_LANES = 4


@dataclass
class LaneResult:
    """What one retrieval lane produced."""

    name: str
    label: str
    block: str = ""
    count: int = 0
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and self.count > 0


@dataclass
class FanoutResult:
    context_block: str
    lanes: list[LaneResult]

    @property
    def total_sources(self) -> int:
        return sum(lane.count for lane in self.lanes)


async def _guarded(name: str, label: str, fn, *args) -> LaneResult:
    """Run a blocking retrieval in a worker thread under a timeout."""
    timeout = max(1, int(orch_config.RESEARCH_LANE_TIMEOUT_SECONDS))
    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(fn, *args), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning("Research lane %s timed out after %ss", name, timeout)
        return LaneResult(name=name, label=label, timed_out=True)
    except Exception as exc:  # noqa: BLE001 - a lane must never break the turn
        logger.warning("Research lane %s failed: %s", name, exc)
        return LaneResult(name=name, label=label, error=f"{type(exc).__name__}: {exc}")


# ── Lanes (blocking; each returns raw results, records nothing) ──────────────
def _fetch_regulatory(query: str, route: RouteDecision) -> LaneResult:
    from app.database import SessionLocal
    from app.services.regulatory_rag_service import search_regulatory

    label = "Regulatory corpus" + (
        f" · {', '.join(route.domains)}" if route.domains else ""
    )
    db = SessionLocal()
    try:
        clauses = search_regulatory(
            db,
            query,
            domains=route.domains or None,
            include_superseded=route.include_superseded,
            top_k=orch_config.REGULATORY_RAG_MAX_RESULTS,
        )
    finally:
        db.close()
    return LaneResult(
        name="regulatory",
        label=label,
        count=len(clauses),
        items=[{"clauses": clauses}] if clauses else [],
    )


def _fetch_primary_sources(query: str, route: RouteDecision) -> LaneResult:
    from app.orchestrator.tools.web_search import run_web_search

    hosts = route.site_hosts[:_MAX_SITE_HOSTS]
    if not orch_config.WEB_SEARCH_ENABLED:
        return LaneResult(
            name="primary_sources",
            label="Official sources · " + (", ".join(hosts) if hosts else "none"),
            error="web search disabled",
        )
    results = run_web_search(query, domains=hosts) if hosts else []
    return LaneResult(
        name="primary_sources",
        label="Official sources · " + (", ".join(hosts) if hosts else "none"),
        count=len(results),
        items=results,
    )


def _fetch_open_web(query: str, _route: RouteDecision) -> LaneResult:
    from app.orchestrator.tools.web_search import run_web_search

    if not orch_config.WEB_SEARCH_ENABLED:
        return LaneResult(name="open_web", label="Open web", error="web search disabled")
    results = run_web_search(query)
    return LaneResult(
        name="open_web", label="Open web", count=len(results), items=results
    )


# ── Orchestration ───────────────────────────────────────────────────────────
def plan_lanes(route: RouteDecision) -> list[tuple[str, str, object]]:
    """Which lanes to run for this query, in citation order."""
    lanes: list[tuple[str, str, object]] = []
    if route.use_regulatory and orch_config.REGULATORY_RAG_ENABLED:
        lanes.append(("regulatory", "Regulatory corpus", _fetch_regulatory))
    if route.site_hosts:
        lanes.append(("primary_sources", "Official sources", _fetch_primary_sources))
    lanes.append(("open_web", "Open web", _fetch_open_web))
    return lanes


async def run_fanout(query: str, route: RouteDecision) -> FanoutResult:
    """Fetch every relevant lane concurrently, then record sources in lane order."""
    lanes = plan_lanes(route)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LANES)

    async def _run(name: str, label: str, fn) -> LaneResult:
        async with semaphore:
            return await _guarded(name, label, fn, query, route)

    results: list[LaneResult] = list(
        await asyncio.gather(*(_run(n, l, f) for n, l, f in lanes))
    )

    # Record + format sequentially: citation numbers are absolute per turn.
    blocks: list[str] = []
    for lane in results:
        if not lane.ok:
            continue
        try:
            lane.block = _record_and_format(lane)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Recording lane %s failed: %s", lane.name, exc)
            lane.error = f"{type(exc).__name__}: {exc}"
            continue
        if lane.block:
            blocks.append(lane.block)

    return FanoutResult(context_block="\n\n".join(blocks), lanes=results)


def _record_and_format(lane: LaneResult) -> str:
    if lane.name == "regulatory":
        from app.services.regulatory_rag_service import format_clauses_for_model

        clauses = lane.items[0]["clauses"] if lane.items else []
        return format_clauses_for_model("the question below", clauses)

    from app.orchestrator.tools.web_search import (
        format_web_results,
        record_web_sources,
    )

    recorded = record_web_sources(lane.items)
    heading = (
        "Official regulator sites" if lane.name == "primary_sources" else "Open web"
    )
    return f"{heading}:\n{format_web_results(recorded)}"


def plan_detail(query: str, route: RouteDecision, lanes: list[LaneResult] | None = None) -> str:
    """Markdown for the Thoughts panel: what was actually searched, not a template."""
    q = " ".join((query or "").strip().split())
    short = q if len(q) <= 160 else q[:157] + "…"
    out = [
        "Running a parallel research pass.",
        "",
        f"**Question focus:** {short or 'the user’s request'}",
        "",
        f"**Sources selected:** {route.summary}",
    ]
    if route.matched_tags:
        out.append(f"**Matched topics:** {', '.join(route.matched_tags[:8])}")
    if route.include_superseded:
        out.append(
            "**Historical question** — superseded provisions are included on purpose."
        )
    if lanes:
        out.append("")
        out.append("### Lanes")
        for lane in lanes:
            if lane.timed_out:
                state = "timed out"
            elif lane.error == "web search disabled":
                state = "web search disabled"
            elif lane.error:
                state = "failed"
            elif lane.count:
                state = f"{lane.count} result(s)"
            else:
                state = "nothing found"
            out.append(f"- {lane.label} — {state}")
    return "\n".join(out)
