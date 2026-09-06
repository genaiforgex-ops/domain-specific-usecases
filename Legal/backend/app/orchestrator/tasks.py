"""Public orchestrator task API — replaces ``get_ai_service()`` for LLM work.

Call sites pass ``module`` + ``operation``; ``rules.classify`` picks the agent
(rule-based, never an LLM). Stub backend returns deterministic shapes.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.orchestrator.agents import (
    build_docx_edit_agent,
    build_edit_agent,
    build_email_reply_agent,
    build_email_task_agent,
    build_legal_qa_agent,
    build_news_analysis_agent,
    build_research_agent,
    build_review_agent,
)
from app.orchestrator.agents.builders import build_change_summary_agent
from app.orchestrator.rules import AgentId, classify
from app.orchestrator.schemas import (
    ChangeSummaryResult,
    DocumentEdit,
    DocxEditPlan,
    EmailReplyDraft,
    EmailTaskExtractionResult,
    LegalQAResult,
    NewsAnalysisResult,
    ResearchNoteResult,
    ReviewResult,
)
from app.orchestrator.task_runner import is_stub_backend, run_structured
from app.orchestrator.prompts.review_context import build_review_context
from app.services.ai_service import (
    ClauseAnalysis,
    ContractAnalysisResult,
    DiffBlock,
    DocxEditPlanResult,
    DocxOperationItem,
    DocumentEditResult,
    EditChange,
    EmailReplyResult,
    ExtractedTask,
    LegalBotResult,
    NegotiationChangeItem,
    NegotiationChangeSummary,
    NewsAnalysis,
    ResearchResult,
    RiskFlag,
    StubLegalAIService,
)
from app.services.docx_structure_service import DocumentStructure, parts_for_ai, relevant_text_excerpt

logger = logging.getLogger("legalos.orchestrator")

_MAX_DRAFT = 60_000
_stub_svc: StubLegalAIService | None = None


def _stub() -> StubLegalAIService:
    global _stub_svc
    if _stub_svc is None:
        _stub_svc = StubLegalAIService(model_version=settings.model_version)
    return _stub_svc


def model_version() -> str:
    if is_stub_backend():
        return settings.model_version
    backend = settings.ai_backend.lower()
    if backend == "adk":
        return "legalos-adk-0.1" if settings.model_version == "legalos-stub-0.1" else settings.model_version
    return settings.model_version


# ── Deterministic (non-LLM) ────────────────────────────────────────────────────


def compare_documents(v1_text: str, v2_text: str) -> Any:
    return _stub().compare_documents(v1_text, v2_text)


def score_task_priority(
    title: str,
    description: str | None,
    sender_email: str | None,
    due_date: Any,
) -> tuple[str, float, str]:
    return _stub().score_task_priority(title, description, sender_email, due_date)


# ── Review ─────────────────────────────────────────────────────────────────────


def review_contract(
    raw_text: str,
    playbook: Sequence[Any],
    contract_type: str = "MSA",
    *,
    module: str,
    operation: str = "review_contract",
    user_id: int | None = None,
    db: Session | None = None,
) -> ContractAnalysisResult:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().review_contract(raw_text, playbook, contract_type)
    try:
        prompt = (
            f"{build_review_context(contract_type, playbook)}\n\n"
            f"THE COUNTERPARTY DRAFT:\n{raw_text[:_MAX_DRAFT]}"
        )
        result = run_structured(
            agent=build_review_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=ReviewResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("review_contract failed (%s), stub fallback: %s", agent_id, exc)
        return _stub().review_contract(raw_text, playbook, contract_type)

    clauses = [
        ClauseAnalysis(
            order_index=c.order_index,
            heading=c.heading,
            clause_text=c.clause_text,
            risk_flag=c.risk_flag,
            confidence=c.confidence,
            rationale=c.rationale,
            suggestion=c.suggestion or c.proposed_text,
            references=[],
            original_text=c.original_text,
            proposed_text=c.proposed_text or c.suggestion,
            category=c.category,
            playbook_clause_type=c.playbook_clause_type,
            standard_position_excerpt=c.standard_position_excerpt,
            regulatory_ref=c.regulatory_ref,
        )
        for c in result.clauses
        if c.risk_flag != "none"
    ]
    next_index = max((cl.order_index for cl in clauses), default=-1) + 1
    for i, missing in enumerate(result.missing_clauses):
        clauses.append(
            ClauseAnalysis(
                order_index=next_index + i,
                heading=f"MISSING: {missing}",
                clause_text="(Required by our standard position but absent from the draft.)",
                risk_flag="high",
                confidence=0.8,
                rationale="Required by our standard position but absent from the draft.",
                suggestion=f"Insert a standard {missing} clause.",
                references=[],
                proposed_text=f"[Standard {missing} clause per JFPSL playbook]",
                category="missing_clause",
            )
        )
    return ContractAnalysisResult(
        clauses=clauses, risk_score=result.risk_score, model_version=model_version()
    )


# ── Edit ───────────────────────────────────────────────────────────────────────


def edit_document(
    base_text: str,
    instruction: str,
    selection: str | None = None,
    *,
    module: str = "contract_review",
    operation: str = "prompt_edit",
    user_id: int | None = None,
    db: Session | None = None,
) -> DocumentEditResult:
    from app.orchestrator.task_runner import TaskBlockedError
    from app.services.edit_instruction import EditInstructionRejected, assert_edit_instruction_allowed

    assert_edit_instruction_allowed(instruction)
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().edit_document(base_text, instruction, selection)
    try:
        prompt = (
            f"INSTRUCTION:\n{instruction}\n\n"
            + (f"SELECTION (apply within this only):\n{selection}\n\n" if selection else "")
            + f"CURRENT DOCUMENT:\n{base_text[:_MAX_DRAFT]}"
        )
        edit = run_structured(
            agent=build_edit_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=DocumentEdit,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
    except (TaskBlockedError, EditInstructionRejected):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("edit_document failed, stub fallback: %s", exc)
        return _stub().edit_document(base_text, instruction, selection)
    return DocumentEditResult(
        edited_text=edit.edited_text,
        change_summary=edit.change_summary,
        changes=[
            EditChange(description=c.description, original=c.original, revised=c.revised)
            for c in edit.changes
        ],
        model_version=model_version(),
    )


def plan_docx_operations(
    structure: dict[str, Any],
    instruction: str,
    selection: str | None = None,
    edit_memory: list[str] | None = None,
    full_text: str | None = None,
    *,
    module: str = "msa_automation",
    operation: str = "prompt_edit",
    user_id: int | None = None,
    db: Session | None = None,
) -> DocxEditPlanResult:
    from app.orchestrator.task_runner import TaskBlockedError
    from app.services.edit_instruction import EditInstructionRejected, assert_edit_instruction_allowed

    assert_edit_instruction_allowed(instruction)
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().plan_docx_operations(
            structure, instruction, selection, edit_memory, full_text
        )
    try:
        memory_block = ""
        if edit_memory:
            memory_block = "EDIT MEMORY:\n" + "\n".join(f"- {m}" for m in edit_memory) + "\n\n"
        document_text = relevant_text_excerpt(
            full_text or structure.get("full_text") or "",
            instruction,
            max_chars=12_000,
        )
        parts_json = parts_for_ai(DocumentStructure.from_dict(structure))
        prompt = (
            f"INSTRUCTION:\n{instruction}\n\n"
            + (f"SELECTION:\n{selection}\n\n" if selection else "")
            + memory_block
            + f"DOCUMENT PARTS:\n{parts_json}\n\n"
            + f"RELEVANT DOCUMENT EXCERPT:\n{document_text}"
        )
        plan = run_structured(
            agent=build_docx_edit_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=DocxEditPlan,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
    except (TaskBlockedError, EditInstructionRejected):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("plan_docx_operations failed, stub fallback: %s", exc)
        fb = _stub().plan_docx_operations(
            structure, instruction, selection, edit_memory, full_text
        )
        fb.used_fallback = True
        return fb
    return DocxEditPlanResult(
        change_summary=plan.change_summary,
        operations=[
            DocxOperationItem(
                op_type=op.op_type,
                anchor_id=op.anchor_id,
                after_anchor_id=op.after_anchor_id,
                target_text=op.target_text,
                content=op.content,
                description=op.description,
                confidence=op.confidence,
            )
            for op in plan.operations
        ],
        model_version=model_version(),
    )


# ── Gmail ──────────────────────────────────────────────────────────────────────


def generate_email_reply(
    latest_body: str,
    original_subject: str,
    from_addr: str,
    prior_summary: str = "",
    user_feedback: str | None = None,
    *,
    module: str = "gmail",
    operation: str = "generate_reply",
    user_id: int | None = None,
    db: Session | None = None,
) -> EmailReplyResult:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().generate_email_reply(
            latest_body, original_subject, from_addr, prior_summary, user_feedback
        )
    try:
        feedback_block = ""
        if user_feedback and user_feedback.strip():
            feedback_block = f"\nLAWYER INSTRUCTIONS:\n{user_feedback.strip()}\n"
        prior_block = ""
        if prior_summary.strip():
            prior_block = (
                "\nPRIOR THREAD SUMMARY (context only):\n" f"{prior_summary.strip()}\n"
            )
        prompt = (
            f"SUBJECT: {original_subject}\nFROM: {from_addr}\n{prior_block}\n"
            f"LATEST MESSAGE TO REPLY TO:\n{latest_body[:12_000]}\n{feedback_block}"
        )
        draft = run_structured(
            agent=build_email_reply_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=EmailReplyDraft,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        subject = draft.subject.strip()
        if not subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}" if original_subject else subject
        body = draft.body.strip()
        if not body:
            raise ValueError("empty reply body")
        return EmailReplyResult(
            subject=subject[:500],
            body=body[:12_000],
            confidence=min(max(draft.confidence, 0.0), 1.0),
            rationale=draft.rationale,
            model_version=model_version(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("generate_email_reply failed, stub fallback: %s", exc)
        return _stub().generate_email_reply(
            latest_body, original_subject, from_addr, prior_summary, user_feedback
        )


def extract_tasks_from_email(
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    thread_summary: str = "",
    allow_fallback: bool = True,
    *,
    module: str = "tasks",
    operation: str = "extract_from_email",
    user_id: int | None = None,
    db: Session | None = None,
) -> list[ExtractedTask]:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().extract_tasks_from_email(
            sender_name, sender_email, subject, body, thread_summary, allow_fallback
        )
    try:
        context = f"\nPRIOR THREAD CONTEXT:\n{thread_summary.strip()}\n" if thread_summary.strip() else ""
        prompt = (
            f"FROM: {sender_name} <{sender_email}>\nSUBJECT: {subject}\n{context}\n"
            f"BODY:\n{body[:8_000]}\n"
        )
        result = run_structured(
            agent=build_email_task_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=EmailTaskExtractionResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        out: list[ExtractedTask] = []
        for t in result.tasks:
            if t.confidence < 0.5:
                continue
            out.append(
                ExtractedTask(
                    title=t.title[:200],
                    description=t.description,
                    priority=t.priority_hint,
                    priority_score={"P0": 90, "P1": 70, "P2": 40, "P3": 20}.get(t.priority_hint, 40),
                    confidence=t.confidence,
                    rationale="Extracted from email by orchestrator email_tasks agent",
                    due_date=None,
                    tags=["email"],
                    estimated_minutes=t.estimated_minutes,
                    model_version=model_version(),
                )
            )
        return out[:3]
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_tasks_from_email failed, stub fallback: %s", exc)
        if not allow_fallback:
            raise
        return _stub().extract_tasks_from_email(
            sender_name, sender_email, subject, body, thread_summary, allow_fallback
        )


# ── News / research / legal QA ─────────────────────────────────────────────────


def analyse_regulatory_update(
    source: str,
    title: str,
    full_text: str,
    *,
    module: str = "legal_news",
    operation: str = "analyse_regulatory_update",
    user_id: int | None = None,
    db: Session | None = None,
) -> NewsAnalysis:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().analyse_regulatory_update(source, title, full_text)
    try:
        prompt = f"SOURCE REGULATOR: {source}\nTITLE: {title}\n\nBODY:\n{(full_text or '')[:20000]}"
        r = run_structured(
            agent=build_news_analysis_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=NewsAnalysisResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        return NewsAnalysis(
            summary=r.summary,
            tags=r.tags,
            relevance_score=r.relevance_score,
            model_version=model_version(),
            category=r.category or "Other",
            impact_note=r.impact_note or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyse_regulatory_update failed, stub fallback: %s", exc)
        return _stub().analyse_regulatory_update(source, title, full_text)


def answer_legal_bot(
    question: str,
    knowledge_base: Sequence[Any],
    *,
    module: str = "legal_bot",
    operation: str = "answer_query",
    user_id: int | None = None,
    db: Session | None = None,
    document_text: str | None = None,
    memory_snippets: list[str] | None = None,
) -> LegalBotResult:
    agent_id = classify(module, operation)
    if is_stub_backend():
        if document_text:
            return _stub().answer_legal_bot_with_document(
                question, knowledge_base, document_text, memory_snippets
            )
        return _stub().answer_legal_bot(question, knowledge_base)

    q_lc = question.lower()
    scored: list[tuple[Any, int]] = []
    for entry in knowledge_base:
        kws = [k.lower() for k in (getattr(entry, "keywords", []) or [])]
        hits = sum(1 for kw in kws if kw and kw in q_lc)
        if hits or any(
            t in (entry.question + " " + (entry.answer or "")).lower()
            for t in re.split(r"\W+", q_lc)
            if len(t) > 3
        ):
            scored.append((entry, hits))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:6]
    kb_payload = [
        {
            "id": getattr(e, "id", None),
            "question": e.question,
            "answer": e.answer,
            "citations": list(e.citations or []),
        }
        for e, _ in top
    ]
    doc_block = ""
    if document_text:
        doc_block = f"\nDOCUMENT CONTEXT:\n{document_text[:12000]}\n"
    mem_block = ""
    if memory_snippets:
        mem_block = "\nMEMORY:\n" + "\n".join(memory_snippets)[:2000] + "\n"
    try:
        prompt = (
            f"Knowledge base:\n{json.dumps(kb_payload, ensure_ascii=False)}\n"
            f"{doc_block}{mem_block}\nQuestion: {question}"
        )
        r = run_structured(
            agent=build_legal_qa_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=LegalQAResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        citations: list[dict[str, Any]] = []
        for e, _ in top:
            for c in e.citations or []:
                citations.append(c)
        for note in r.citation_notes:
            citations.append({"reference": note})
        tier = 2 if r.should_escalate or r.confidence < 0.55 else 1
        return LegalBotResult(
            answer=r.answer.strip() or "Unable to formulate an answer; escalating.",
            citations=citations,
            confidence=round(max(0.0, min(1.0, r.confidence)), 2),
            tier=tier,
            model_version=model_version(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("answer_legal_bot failed, stub fallback: %s", exc)
        if document_text:
            return _stub().answer_legal_bot_with_document(
                question, knowledge_base, document_text, memory_snippets
            )
        return _stub().answer_legal_bot(question, knowledge_base)


def generate_research_note(
    query: str,
    regulatory_corpus: Sequence[Any],
    *,
    module: str = "legal_research",
    operation: str = "generate_research_note",
    user_id: int | None = None,
    db: Session | None = None,
) -> ResearchResult:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().generate_research_note(query, regulatory_corpus)
    corpus_payload = []
    for src in list(regulatory_corpus)[:12]:
        corpus_payload.append(
            {
                "title": getattr(src, "title", None) or getattr(src, "name", ""),
                "regulator": getattr(src, "regulator", "") or getattr(src, "source", ""),
                "excerpt": (getattr(src, "full_text", None) or getattr(src, "summary", "") or "")[
                    :2000
                ],
            }
        )
    try:
        prompt = (
            f"Query: {query}\n\nCorpus excerpts:\n"
            f"{json.dumps(corpus_payload, ensure_ascii=False)}"
        )
        r = run_structured(
            agent=build_research_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=ResearchNoteResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        return ResearchResult(
            summary=r.summary,
            applicable_regulations=[{"name": x} for x in r.applicable_regulations],
            key_provisions=[{"text": x} for x in r.key_provisions],
            implications=r.implications,
            recommended_next_steps=r.recommended_next_steps,
            citations=[{"reference": x} for x in r.applicable_regulations],
            confidence=r.confidence,
            model_version=model_version(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("generate_research_note failed, stub fallback: %s", exc)
        return _stub().generate_research_note(query, regulatory_corpus)


def summarize_document_changes(
    v1_text: str,
    v2_text: str,
    diff_blocks: list[DiffBlock],
    risk_commentary: list[RiskFlag],
    contract_type: str = "MSA",
    *,
    module: str = "msa_automation",
    operation: str = "compare_documents",
    user_id: int | None = None,
    db: Session | None = None,
) -> NegotiationChangeSummary:
    agent_id = classify(module, operation)
    if is_stub_backend():
        return _stub().summarize_document_changes(
            v1_text, v2_text, diff_blocks, risk_commentary, contract_type
        )
    try:
        material = [
            {"kind": b.kind, "v1": (b.v1 or "")[:400], "v2": (b.v2 or "")[:400]}
            for b in diff_blocks
            if b.kind != "equal"
        ][:40]
        risks = [
            {"severity": r.severity, "excerpt": r.excerpt, "rationale": r.rationale}
            for r in risk_commentary[:20]
        ]
        prompt = (
            f"Contract type: {contract_type}\n"
            f"Diff blocks:\n{json.dumps(material, ensure_ascii=False)}\n"
            f"Risk flags:\n{json.dumps(risks, ensure_ascii=False)}"
        )
        r = run_structured(
            agent=build_change_summary_agent(),
            agent_id=agent_id,
            prompt=prompt,
            schema=ChangeSummaryResult,
            module=module,
            operation=operation,
            user_id=user_id,
            db=db,
        )
        changes = [
            NegotiationChangeItem(
                diff_index=i,
                title=c.title,
                old_text=c.old_text,
                new_text=c.new_text,
                severity=c.severity,
                impact=c.impact,
                suggested_action=c.suggested_action,
                clause_ref=c.clause_ref,
                change_summary=c.change_summary,
                rationale=c.rationale,
            )
            for i, c in enumerate(r.changes)
        ]
        return NegotiationChangeSummary(
            changes=changes,
            executive_summary=r.executive_summary,
            model_version=model_version(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarize_document_changes failed, stub fallback: %s", exc)
        return _stub().summarize_document_changes(
            v1_text, v2_text, diff_blocks, risk_commentary, contract_type
        )
