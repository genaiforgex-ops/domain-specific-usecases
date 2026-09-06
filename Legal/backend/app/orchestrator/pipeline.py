"""The chat request pipeline.

Orchestrates one turn end-to-end and yields SSE frames. Order (per the
chatbot_skills blueprint):

  1. Resolve session (create ADK session if new).
  2. Resolve attached / @-mentioned context (existing LegalOS services).
  3. Input armor: PII mask → injection screen. Block short-circuits here.
  4. Build the model message (context block + <current_user_query> wrapper).
  5. runner.run_async streaming → emit thinking / partial frames.
  6. Output armor: sanitize + PII restore on the assembled final text.
  7. Persist turn metrics + session index + audit (off the event loop).
  8. Emit the final frame (+ optional headline).

No domain logic lives here — only orchestration. Domain reasoning is in the
sub-agents; retrieval is in `context.py`; safety is in `guardrails/`.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncIterator

import anyio
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.errors.already_exists_error import AlreadyExistsError
from google.genai import types

from app.database import SessionLocal
from app.orchestrator import config as orch_config
from app.orchestrator import sse
from app.orchestrator.context import resolve_context
from app.orchestrator.dependencies import get_runner, get_session_service
from app.orchestrator.guardrails import mask_pii, restore_pii, sanitize_output, screen_input
from app.orchestrator.guardrails.armor import REFUSAL_MESSAGE
from app.orchestrator.memory import record_turn, upsert_session
from app.orchestrator.models import ContextRef
from app.orchestrator.runtime import request_runtime
from app.orchestrator.sources import (
    collected_sources,
    record_sources,
    start_collection,
    stop_collection,
)
from app.services.audit_service import write_audit

logger = logging.getLogger("legalos.orchestrator")

_STREAMING = RunConfig(streaming_mode=StreamingMode.SSE)


def _resolve_context_sync(user_id: int, refs: list[ContextRef]) -> tuple[str, list[dict]]:
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return "", []
        return resolve_context(db, user, refs, max_chars=orch_config.MAX_CONTEXT_CHARS)
    finally:
        db.close()


def _persist_turn_sync(
    *,
    user_id: int,
    ip: str | None,
    http_session_id: str | None,
    session_id: str,
    user_query: str,
    bot_response: str,
    agent_name: str | None,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int | None,
    blocked: bool,
    sources: list[dict] | None = None,
    thoughts: list[dict] | None = None,
    mode: str | None = None,
    tokens_estimated: bool = False,
    latency_phases: dict[str, int] | None = None,
    turn_status: str | None = None,
) -> int | None:
    from app.models.user import User
    from app.orchestrator.metrics import record_llm_call, task_usage

    db = SessionLocal()
    try:
        upsert_session(db, session_id, user_id, user_query)
        turn = record_turn(
            db,
            session_id=session_id,
            user_id=user_id,
            user_query=user_query,
            bot_response=bot_response,
            agent_name=agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            blocked=blocked,
            sources=sources,
            thoughts=thoughts,
            mode=mode,
        )
        user = db.get(User, user_id)
        extra = {
            "chat_session_id": session_id,
            "agent": agent_name,
            "blocked": blocked,
            "tokens_estimated": tokens_estimated,
            "turn_status": turn_status or ("blocked" if blocked else "ok"),
        }
        if latency_phases:
            extra["latency_phases"] = latency_phases
        write_audit(
            db,
            user=user,
            action_type="chat_turn",
            module="orchestrator",
            input_summary=user_query[:500],
            ai_output_summary=(bot_response or "")[:500],
            model_version=orch_config.APP_NAME,
            ip_address=ip,
            session_id=http_session_id,
            extra=extra,
        )
        with task_usage(
            db,
            user_id=user_id,
            module="orchestrator",
            operation=f"chat_{mode or 'review'}",
            agent_name=agent_name or "chat",
            model_version=orch_config.APP_NAME,
        ):
            record_llm_call(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated=tokens_estimated,
            )
        db.commit()
        return turn.id
    except Exception:  # noqa: BLE001 — never let logging failure sink the turn
        db.rollback()
        logger.exception("[orchestrator] persist turn failed for session %s", session_id)
        return None
    finally:
        db.close()


async def _ensure_session(session_service, session_id: str | None, user_id: str) -> str:
    sid = (session_id or uuid.uuid4().hex).strip() or uuid.uuid4().hex
    existing = await session_service.get_session(
        app_name=orch_config.APP_NAME, user_id=user_id, session_id=sid
    )
    if existing is None:
        try:
            await session_service.create_session(
                app_name=orch_config.APP_NAME, user_id=user_id, session_id=sid
            )
        except AlreadyExistsError:
            pass
    return sid


_MODE_DIRECTIVES = {
    "review": (
        "Mode: REVIEW. Prefer attached documents and JFPSL legal-template "
        "search (search_jfpsl_knowledge) before any web search. Quote the "
        "exact text you rely on. Use web_search only when the answer cannot "
        "be grounded in attachments or the JFPSL / regulatory corpus. Keep tool "
        "use lean (few hops). Give a thorough, topic-complete answer; use tables "
        "for comparisons; close with Summary/Conclusion, Next steps, and "
        "Suggested follow-up questions (see Response Style)."
    ),
    "research": (
        "Mode: RESEARCH. Multi-source research. Call "
        "search_regulatory_knowledge FIRST for law/regulator questions. For "
        "current, regulatory, or public-law questions, call web_search (and "
        "web_fetch on authoritative URLs when snippets are thin). Use "
        "search_jfpsl_knowledge when JFPSL templates or internal positions are "
        "relevant, as a secondary source. Cover jurisdiction, related "
        "sub-topics, and practical implications; cite authorities you actually "
        "retrieved; do not fabricate circular numbers or dates. Prefer a "
        "detailed answer with tables where useful; close with "
        "Summary/Conclusion, Next steps, and Suggested follow-up questions."
    ),
    "research_with_preretrieved": (
        "Mode: RESEARCH. Pre-retrieved numbered sources are already in this "
        "message — synthesize and cite them by bracket number first. Call "
        "web_search or search_jfpsl_knowledge only for clear gaps (missing "
        "jurisdiction, very recent circular, or JFPSL template wording). Do not "
        "re-fetch sources you already have. Do not fabricate circular numbers "
        "or dates. Prefer a detailed answer with tables where useful; close "
        "with Summary/Conclusion, Next steps, and Suggested follow-up questions."
    ),
    "draft": (
        "Mode: DRAFT. Help the user draft the requested legal document. If a "
        "template or prior document is attached, follow its structure and "
        "style. If none is attached, call search_jfpsl_knowledge for the closest "
        "JFPSL template before drafting. Deliver a complete, ready-to-edit draft "
        "using [[PLACEHOLDER: description]] markers for party names, dates, "
        "amounts, and other blanks. After the draft, include: (1) a Placeholders "
        "list, (2) a Structure checklist of sections covered vs typical for that "
        "doc type, (3) brief notes on risks. Close with Summary/Conclusion and "
        "Next steps when useful. Do not open-web fish for drafting language."
    ),
}


def _friendly_transfer(agent_name: str | None) -> str:
    mapping = {
        "contract_agent": "Reviewing the contract details…",
        "compliance_agent": "Checking the regulatory position…",
        "discovery_agent": "Looking that up…",
    }
    return mapping.get(agent_name or "", "Let me look into that…")


def _research_plan_detail(query: str) -> str:
    """LawGenie-original research outline from the user question (no third-party copy)."""
    q = " ".join((query or "").strip().split())
    short = q if len(q) <= 160 else q[:157] + "…"
    return (
        "Starting a multi-source research pass for LawGenie.\n\n"
        f"**Question focus:** {short or 'the user’s request'}\n\n"
        "### Jurisdiction & scope\n"
        "- Identify the governing jurisdiction and relevant regulators\n"
        "- Note whether Indian law, foreign law, or cross-border rules apply\n\n"
        "### Sub-topics to cover\n"
        "- Core statutory / regulatory requirements\n"
        "- Recent circulars, guidance, or enforcement signals\n"
        "- Practical implications for JFPSL contracting and compliance\n"
    )


def _thought_items_from_sources(items: list[dict], *, limit: int = 8) -> list[dict]:
    out: list[dict] = []
    for s in items[:limit]:
        title = (s.get("title") or s.get("url") or s.get("storage_key") or "").strip()
        if not title:
            continue
        out.append(
            {
                "title": title,
                "url": s.get("url") or None,
                "storage_key": s.get("storage_key") or None,
                "kind": s.get("kind"),
            }
        )
    return out


async def run_chat_stream(
    *,
    user_id: int,
    role: str,
    ip: str | None,
    http_session_id: str | None,
    text: str,
    session_id: str | None,
    context_refs: list[ContextRef],
    generate_headline: bool,
    mode: str = "review",
    disconnect_check=None,
) -> AsyncIterator[str]:
    session_service = get_session_service()
    runner = get_runner()
    adk_user = str(user_id)
    start = time.perf_counter()
    t_fanout_ms = 0
    t_agent_ms = 0
    t_verify_ms = 0
    tokens_estimated = False
    turn_status = "ok"
    cancelled = False
    persisted = False

    async with session_service.request_scope():
        sid = await _ensure_session(session_service, session_id, adk_user)

        # (2) Resolve attached / mentioned context off the event loop.
        context_block = ""
        context_sources: list[dict] = []
        if context_refs:
            context_block, context_sources = await anyio.to_thread.run_sync(
                _resolve_context_sync, user_id, context_refs
            )

        # Optional belt-and-braces transcript when compaction is off.
        history_block = ""
        if orch_config.HISTORY_TURNS_FOR_CONTEXT > 0:
            from app.orchestrator.memory import load_history_text

            def _load_hist() -> str:
                db = SessionLocal()
                try:
                    return load_history_text(
                        db, sid, user_id, orch_config.HISTORY_TURNS_FOR_CONTEXT
                    )
                finally:
                    db.close()

            history_block = await anyio.to_thread.run_sync(_load_hist)

        # (3) Input armor: mask PII across BOTH the query and the context, then screen.
        combined_for_mask = f"{context_block}\n\n{text}" if context_block else text
        if history_block:
            combined_for_mask = f"Prior turns:\n{history_block}\n\n{combined_for_mask}"
        masked_combined, pii_map = (
            mask_pii(combined_for_mask)
            if orch_config.PII_MASKING_ENABLED
            else (combined_for_mask, {})
        )
        verdict = screen_input(masked_combined, enabled=orch_config.ARMOR_ENABLED)
        if verdict.blocked:
            yield sse.thinking("Reviewing your request…")
            await anyio.to_thread.run_sync(
                lambda: _persist_turn_sync(
                    user_id=user_id,
                    ip=ip,
                    http_session_id=http_session_id,
                    session_id=sid,
                    user_query=text,
                    bot_response=REFUSAL_MESSAGE,
                    agent_name=None,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    blocked=True,
                    mode=mode,
                    turn_status="blocked",
                )
            )
            yield sse.safety_block(REFUSAL_MESSAGE, sid)
            return

        # (4) Build the message. Re-split the masked combined text so the model
        # sees masked context + masked query, with the query fenced for injection
        # hardening.
        directive = _MODE_DIRECTIVES.get(mode, _MODE_DIRECTIVES["review"])
        masked_context = ""
        masked_query = masked_combined
        if context_block:
            masked_context, masked_query = masked_combined.rsplit("\n\n", 1)
            message_text = (
                f"{directive}\n\nUse the following context to answer.\n{masked_context}\n\n"
                f"<current_user_query>\n{masked_query}\n</current_user_query>"
            )
        else:
            message_text = (
                f"{directive}\n\n<current_user_query>\n{masked_combined}\n</current_user_query>"
            )

        content = types.Content(role="user", parts=[types.Part(text=message_text)])

        # (5) Stream.
        full_text = ""
        last_partial = ""
        last_agent: str | None = None
        input_tokens = 0
        output_tokens = 0
        transfer_announced: set[str] = set()
        thoughts: list[dict] = []
        thought_seq = 0
        sources_seen = 0
        sources: list[dict] = []

        def _push_thought(
            *,
            kind: str,
            detail: str | None = None,
            items: list[dict] | None = None,
            title: str = "Thinking",
        ) -> str:
            nonlocal thought_seq
            thought_seq += 1
            tid = f"t{thought_seq}"
            step: dict = {"id": tid, "kind": kind, "title": title}
            if detail:
                step["detail"] = detail
            if items:
                step["items"] = items
            thoughts.append(step)
            return sse.thought(
                thought_id=tid,
                kind=kind,
                title=title,
                detail=detail,
                items=items,
            )

        async def _persist(
            bot_response: str,
            *,
            blocked: bool = False,
            status: str = "ok",
        ) -> int | None:
            nonlocal persisted, tokens_estimated
            if persisted:
                return None
            phases = {
                "fanout_ms": t_fanout_ms,
                "agent_ms": t_agent_ms,
                "verify_ms": t_verify_ms,
                "total_ms": int((time.perf_counter() - start) * 1000),
            }
            if any(phases.values()):
                thoughts.append(
                    {
                        "id": "latency",
                        "kind": "status",
                        "title": "Latency",
                        "detail": (
                            f"fanout={phases['fanout_ms']}ms · "
                            f"agent={phases['agent_ms']}ms · "
                            f"verify={phases['verify_ms']}ms · "
                            f"total={phases['total_ms']}ms"
                        ),
                    }
                )
            est_in = False
            est_out = False
            nonlocal input_tokens, output_tokens
            if not output_tokens:
                output_tokens = max(1, len(bot_response or "") // 4)
                est_out = True
            if not input_tokens:
                input_tokens = max(1, len(message_text) // 4)
                est_in = True
            tokens_estimated = est_in or est_out
            turn_id = await anyio.to_thread.run_sync(
                lambda: _persist_turn_sync(
                    user_id=user_id,
                    ip=ip,
                    http_session_id=http_session_id,
                    session_id=sid,
                    user_query=text,
                    bot_response=bot_response,
                    agent_name=last_agent,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=phases["total_ms"],
                    blocked=blocked,
                    sources=sources or None,
                    thoughts=thoughts or None,
                    mode=mode,
                    tokens_estimated=tokens_estimated,
                    latency_phases=phases,
                    turn_status=status,
                )
            )
            persisted = True
            return turn_id

        # Early Thoughts: research plan vs lean review of attachments.
        research_route = None
        if mode == "research":
            yield sse.thinking("Planning research…")
            if orch_config.RESEARCH_FANOUT_ENABLED:
                from app.orchestrator import research_fanout
                from app.services.regulatory_router import route_query

                research_route = route_query(text)
                yield _push_thought(
                    kind="plan",
                    detail=research_fanout.plan_detail(text, research_route),
                )
            else:
                yield _push_thought(kind="plan", detail=_research_plan_detail(text))
        elif context_refs:
            attach_labels = [
                (r.label or r.kind).strip()
                for r in context_refs
                if (r.label or r.kind)
            ]
            if attach_labels:
                yield sse.thinking("Reading attached materials…")
                yield _push_thought(
                    kind="documents",
                    detail="Reviewing documents provided with this question.",
                    items=[{"title": label} for label in attach_labels[:8]],
                )

        sources_token = start_collection()
        if context_sources:
            record_sources(context_sources)
        try:
            # Research fan-out: retrieve every relevant lane concurrently and hand
            # the agent the text up front, instead of it issuing serial tool calls.
            if research_route is not None:
                yield sse.thinking("Searching the corpus and official sources…")
                t0 = time.perf_counter()
                fanout = await research_fanout.run_fanout(text, research_route)
                t_fanout_ms = int((time.perf_counter() - t0) * 1000)
                retrieved = collected_sources()
                sources_seen = len(retrieved)
                yield _push_thought(
                    kind="search",
                    title="Researched",
                    detail=research_fanout.plan_detail(
                        text, research_route, fanout.lanes
                    ),
                    items=_thought_items_from_sources(retrieved),
                )
                if fanout.context_block:
                    directive = _MODE_DIRECTIVES["research_with_preretrieved"]
                    message_text = (
                        f"{directive}\n\nPre-retrieved sources for this question "
                        "(already numbered for citation — cite these by their "
                        f"bracket numbers):\n{fanout.context_block}\n\n"
                        + (
                            f"Additional context:\n{masked_context}\n\n"
                            if context_block
                            else ""
                        )
                        + f"<current_user_query>\n"
                        + (masked_query if context_block else masked_combined)
                        + "\n</current_user_query>"
                    )
                    content = types.Content(
                        role="user", parts=[types.Part(text=message_text)]
                    )

            with request_runtime(user_id=user_id, role=role, mode=mode):
                from app.orchestrator.runtime import current_runtime

                t_agent0 = time.perf_counter()
                async for event in runner.run_async(
                    user_id=adk_user,
                    session_id=sid,
                    new_message=content,
                    run_config=_STREAMING,
                ):
                    if disconnect_check is not None and await disconnect_check():
                        cancelled = True
                        turn_status = "cancelled"
                        break

                    if event.author and event.author != orch_config.APP_NAME:
                        last_agent = event.author

                    # thinking + structured thoughts: agent transfers / tool calls
                    for part in (event.content.parts if event.content else []) or []:
                        fc = getattr(part, "function_call", None)
                        if fc is not None:
                            args = fc.args or {}
                            if fc.name == "transfer_to_agent":
                                target = args.get("agent_name")
                                if target and target not in transfer_announced:
                                    transfer_announced.add(target)
                                    yield sse.thinking(_friendly_transfer(target))
                                    yield _push_thought(
                                        kind="status",
                                        detail=_friendly_transfer(target),
                                    )
                            elif fc.name == "web_search":
                                query = (args.get("query") or "").strip()
                                yield sse.thinking("Searching the web…")
                                yield _push_thought(
                                    kind="search",
                                    detail=(
                                        f"Searching the web for: {query}"
                                        if query
                                        else "Searching the web…"
                                    ),
                                )
                            elif fc.name == "web_fetch":
                                url = (args.get("url") or "").strip()
                                yield sse.thinking("Reading the full page…")
                                yield _push_thought(
                                    kind="links",
                                    detail=(
                                        f"Fetching full text: {url}"
                                        if url
                                        else "Fetching full page text…"
                                    ),
                                )
                            elif fc.name == "search_regulatory_knowledge":
                                query = (args.get("query") or "").strip()
                                yield sse.thinking("Searching the regulatory corpus…")
                                yield _push_thought(
                                    kind="search",
                                    detail=(
                                        f"Searching regulatory corpus for: {query}"
                                        if query
                                        else "Searching the regulatory corpus…"
                                    ),
                                )
                            elif fc.name == "search_jfpsl_knowledge":
                                query = (args.get("query") or "").strip()
                                yield sse.thinking("Searching legal templates…")
                                yield _push_thought(
                                    kind="search",
                                    detail=(
                                        f"Searching JFPSL legal templates for: {query}"
                                        if query
                                        else "Searching JFPSL legal templates…"
                                    ),
                                )
                            elif fc.name == "get_msa_document":
                                yield sse.thinking("Opening the contract…")
                                yield _push_thought(
                                    kind="documents",
                                    detail="Reading the requested MSA / contract document.",
                                )
                            else:
                                yield sse.thinking("One moment…")

                    # Emit Links/Documents read when tools append new sources.
                    current_sources = collected_sources()
                    if len(current_sources) > sources_seen:
                        new_sources = current_sources[sources_seen:]
                        sources_seen = len(current_sources)
                        web_items = _thought_items_from_sources(
                            [s for s in new_sources if (s.get("kind") or "web") == "web"]
                        )
                        doc_items = _thought_items_from_sources(
                            [s for s in new_sources if (s.get("kind") or "") != "web"]
                        )
                        if web_items:
                            yield _push_thought(
                                kind="links",
                                detail="Links read",
                                items=web_items,
                            )
                        if doc_items:
                            yield _push_thought(
                                kind="documents",
                                detail="Documents read",
                                items=doc_items,
                            )

                    if getattr(event, "usage_metadata", None):
                        um = event.usage_metadata
                        input_tokens = getattr(um, "prompt_token_count", None) or input_tokens
                        output_tokens = getattr(um, "candidates_token_count", None) or output_tokens

                    text_chunk = _event_text(event)
                    if not text_chunk:
                        continue

                    if event.partial:
                        # Do not repair Markdown tables on token deltas. The UI
                        # appends each chunk; normalizing a half-row synthesizes
                        # a separator and the next tokens then glue a broken table.
                        # Frontend Markdown.tsx repairs the accumulated text.
                        cleaned = restore_pii(sanitize_output(text_chunk), pii_map)
                        last_partial = cleaned
                        yield sse.partial(cleaned, sid)
                    elif event.is_final_response():
                        full_text = text_chunk
                t_agent_ms = int((time.perf_counter() - t_agent0) * 1000)

                rt = current_runtime()
                if rt and rt.notes:
                    yield _push_thought(
                        kind="status",
                        title="Corpus freshness",
                        detail="\n".join(rt.notes),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[orchestrator] run failed for session %s: %s", sid, exc)
            stop_collection(sources_token)
            sources = collected_sources()
            err_text = last_partial or full_text or "The assistant hit an error. Please try again."
            await _persist(err_text, status="error")
            yield sse.error("The assistant hit an error. Please try again.")
            await session_service.flush_and_cleanup(sid)
            return

        sources = collected_sources()
        stop_collection(sources_token)

        if cancelled:
            final_text = restore_pii(
                sanitize_output(full_text or last_partial), pii_map
            ).strip()
            if not final_text:
                final_text = "(Generation stopped.)"
            turn_id = await _persist(final_text, status="cancelled")
            yield sse.final(
                final_text,
                sid,
                headline=None,
                sources=sources,
                turn_id=turn_id,
                thoughts=thoughts or None,
            )
            await session_service.flush_and_cleanup(sid)
            return

        final_text = restore_pii(sanitize_output(full_text), pii_map).strip()
        if not final_text:
            final_text = "I couldn't produce a response for that. Could you rephrase?"
        else:
            from app.services.markdown_tables import normalize_markdown_tables

            final_text = normalize_markdown_tables(final_text).strip()

        # Citation audit
        if mode == "research" and orch_config.RESEARCH_VERIFY_ENABLED and sources:
            from app.orchestrator import groundedness

            t_v0 = time.perf_counter()
            audit = await anyio.to_thread.run_sync(
                lambda: groundedness.audit_answer(final_text, sources, user_id=user_id)
            )
            t_verify_ms = int((time.perf_counter() - t_v0) * 1000)
            if audit.ran:
                final_text = audit.text
                detail = groundedness.audit_detail(audit)
                if detail:
                    yield _push_thought(
                        kind="status", title="Citation check", detail=detail
                    )

        turn_id = await _persist(final_text, status=turn_status)

        # (8) Final frame.
        headline = None
        if generate_headline:
            headline = " ".join(text.strip().split())[:60]
        yield sse.final(
            final_text,
            sid,
            headline=headline,
            sources=sources,
            turn_id=turn_id,
            thoughts=thoughts or None,
        )
        await session_service.flush_and_cleanup(sid)


def _event_text(event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))


async def run_chat_once(
    *,
    user_id: int,
    role: str,
    ip: str | None,
    http_session_id: str | None,
    text: str,
    session_id: str | None,
    context_refs: list[ContextRef],
    mode: str = "review",
) -> dict:
    """Non-streaming fallback: run the same pipeline, collect the final frame."""
    final_text = ""
    sid = session_id or ""
    blocked = False
    async for frame in run_chat_stream(
        user_id=user_id,
        role=role,
        ip=ip,
        http_session_id=http_session_id,
        text=text,
        session_id=session_id,
        context_refs=context_refs,
        generate_headline=False,
        mode=mode,
    ):
        # Parse only the terminal data frames we care about.
        if '"partial": false' in frame or '"blocked": true' in frame:
            import json

            payload = json.loads(frame[len("data: ") : frame.index("\n\n")])
            final_text = payload.get("text", final_text)
            sid = payload.get("session_id", sid)
            blocked = payload.get("blocked", False)
    return {"text": final_text, "session_id": sid, "blocked": blocked}
