"""UC-01 Contract Review."""

import difflib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.contract import Contract, ContractClause
from app.models.contract_revision import ContractRevision
from app.models.user import User
from app.schemas.contract import (
    ClauseDecision,
    ContractChangesOut,
    ContractCreate,
    ContractOut,
    ContractRevisionOut,
    ContractRevisionSummary,
    ContractRunReviewRequest,
    ContractSuggestionDecision,
    ContractSuggestionsApply,
    ContractSuggestionsPreview,
    ContractSummary,
    PromptEditCreate,
)
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.msa_risk_service import compute_risk_breakdown
from app.services.msa_version_service import risk_score_from_suggestions
from app.services.review_workspace_service import (
    append_change_entry,
    load_playbook_context,
    normalize_findings,
    playbook_summary,
)
from app.services.suggestion_service import (
    compile_accepted_suggestions,
    filter_actionable_suggestions,
)


def _line_diff(before: str, after: str) -> list[dict]:
    """Line-level redline blocks for track-mode rendering (matches DiffView)."""
    a_lines = before.splitlines()
    b_lines = after.splitlines()
    blocks: list[dict] = []
    # autojunk=False keeps long documents accurate — the default "popular line"
    # heuristic can otherwise mis-align large sections (e.g. the document tail
    # showing up as inserted on every edit).
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=a_lines, b=b_lines, autojunk=False
    ).get_opcodes():
        blocks.append(
            {
                "kind": tag,  # equal | insert | delete | replace
                "v1": "\n".join(a_lines[i1:i2]),
                "v2": "\n".join(b_lines[j1:j2]),
            }
        )
    return blocks


router = APIRouter(prefix="/api/contract-review", tags=["contract-review"])


def _ground_truth_suggestions(text: str, guidelines: str | None) -> list[dict]:
    if not guidelines or not guidelines.strip():
        return []
    findings: list[dict] = []
    text_lc = text.lower()
    for i, raw in enumerate(guidelines.splitlines()):
        expected = raw.strip().strip("-* ")
        if not expected or expected.lower() in text_lc:
            continue
        findings.append(
            {
                "order_index": 9000 + i,
                "heading": f"Ground truth check: {expected[:80]}",
                "clause_text": expected,
                "risk_flag": "high",
                "confidence": 0.95,
                "rationale": "Reviewer ground-truth term not found in document.",
                "ai_suggestion": f"Use exact wording: {expected}",
                "original_text": None,
                "proposed_text": expected,
                "category": "policy",
                "decision": "pending",
            }
        )
    return findings


def _contract_out(contract: Contract, db: Session) -> ContractOut:
    data = ContractOut.model_validate(contract).model_dump()
    suggestions = contract.ai_suggestions or []
    data["risk_breakdown"] = compute_risk_breakdown(
        suggestions,
        guidelines=contract.review_guidelines,
        document_text=contract.raw_text,
        ai_clause_risk=contract.risk_score,
    )
    ctx = load_playbook_context(db, contract.contract_type)
    data["playbook_summary"] = playbook_summary(contract.contract_type, ctx.clauses)
    return ContractOut(**data)


def _run_review_on_contract(contract: Contract, db: Session, guidelines: str | None) -> None:
    ctx = load_playbook_context(db, contract.contract_type)
    reg_block = ""
    if ctx.regulatory_snippets:
        from app.services.review_workspace_service import format_regulatory_context

        reg_block = format_regulatory_context(ctx.regulatory_snippets)
    text_for_review = contract.raw_text
    if reg_block:
        text_for_review = f"{reg_block}\n\n---\n\n{contract.raw_text}"

    result = orch_tasks.review_contract(
        text_for_review,
        ctx.clauses,
        contract_type=contract.contract_type,
        module="contract_review",
        operation="review_contract",
        user_id=contract.uploaded_by_id,
        db=db,
    )
    suggestions = filter_actionable_suggestions(
        normalize_findings(result.clauses, ctx.clauses, ctx.clause_bank)
    )
    effective_guidelines = guidelines if guidelines is not None else contract.review_guidelines
    suggestions.extend(_ground_truth_suggestions(contract.raw_text, effective_guidelines))
    contract.ai_suggestions = suggestions
    contract.risk_score = (
        risk_score_from_suggestions(suggestions) if suggestions else result.risk_score
    )
    contract.model_version = result.model_version
    if contract.status == "pending_review":
        contract.status = "under_review"


@router.get("", response_model=list[ContractSummary])
def list_contracts(
    user: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> list[ContractSummary]:
    rows = db.execute(select(Contract).order_by(Contract.created_at.desc())).scalars().all()
    return [ContractSummary.model_validate(c) for c in rows]


@router.post("", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractOut:
    if not payload.raw_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="raw_text is required")

    contract = Contract(
        filename=payload.filename,
        contract_type=payload.contract_type,
        raw_text=payload.raw_text,
        status="pending_review",
        uploaded_by_id=user.id,
        review_guidelines=payload.review_guidelines,
    )
    db.add(contract)
    db.flush()
    _run_review_on_contract(contract, db, payload.review_guidelines)

    # Legacy clause rows for backward compatibility
    for s in contract.ai_suggestions or []:
        db.add(
            ContractClause(
                contract_id=contract.id,
                order_index=s.get("order_index", 0),
                heading=s.get("heading"),
                clause_text=s.get("clause_text", ""),
                risk_flag=s.get("risk_flag", "none"),
                confidence=s.get("confidence", 0.0),
                ai_rationale=s.get("rationale"),
                ai_suggestion=s.get("ai_suggestion"),
                references=[],
                decision="pending",
            )
        )
    write_audit(
        db,
        user=user,
        action_type="contract_reviewed",
        module="contract_review",
        input_summary=f"filename={payload.filename} chars={len(payload.raw_text)}",
        ai_output_summary=f"risk_score={contract.risk_score} suggestions={len(contract.ai_suggestions or [])}",
        confidence_score=0.8,
        model_version=contract.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract.id,
    )
    db.commit()
    db.refresh(contract)
    return _contract_out(contract, db)


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: int,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return _contract_out(contract, db)


@router.post("/{contract_id}/clauses/{clause_id}/decision", response_model=ContractOut)
def decide_clause(
    contract_id: int,
    clause_id: int,
    payload: ClauseDecision,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ContractOut:
    if payload.decision not in {"accepted", "rejected", "edited"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision")
    clause = db.get(ContractClause, clause_id)
    if clause is None or clause.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    clause.decision = payload.decision
    clause.reviewer_edit = payload.reviewer_edit
    clause.reviewer_comment = payload.reviewer_comment
    write_audit(
        db,
        user=user,
        action_type="clause_decision",
        module="contract_review",
        input_summary=f"clause_id={clause_id} flag={clause.risk_flag}",
        ai_output_summary=(clause.ai_suggestion or "")[:500],
        human_decision=payload.decision,
        confidence_score=clause.confidence,
        model_version=clause.contract.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(clause.contract)
    return _contract_out(clause.contract, db)


@router.post("/{contract_id}/run-review", response_model=ContractOut)
def run_review(
    contract_id: int,
    request: Request,
    payload: ContractRunReviewRequest | None = None,
    user: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractOut:
    body = payload or ContractRunReviewRequest()
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.status == "finalized":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract already finalized")
    if body.review_guidelines is not None:
        contract.review_guidelines = body.review_guidelines
    _run_review_on_contract(contract, db, body.review_guidelines)
    write_audit(
        db,
        user=user,
        action_type="contract_rereview",
        module="contract_review",
        input_summary=f"contract_id={contract_id}",
        model_version=contract.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(contract)
    return _contract_out(contract, db)


@router.post("/{contract_id}/decide", response_model=ContractOut)
def decide_suggestion(
    contract_id: int,
    payload: ContractSuggestionDecision,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ContractOut:
    if payload.decision not in {"accept", "modify", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision")
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.status == "finalized":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract already finalized")
    suggestions = [dict(s) for s in (contract.ai_suggestions or [])]
    updated = False
    for s in suggestions:
        if s.get("order_index") == payload.suggestion_id:
            s["decision"] = payload.decision
            if payload.reviewer_edit is not None:
                s["reviewer_edit"] = payload.reviewer_edit
            updated = True
            contract.change_history = append_change_entry(
                contract.change_history,
                source="ai_suggestion",
                status=payload.decision,
                before=s.get("original_text"),
                after=payload.reviewer_edit or s.get("proposed_text"),
                rationale=s.get("rationale"),
                playbook_clause_id=s.get("playbook_clause_id"),
                decided_by_id=user.id,
                order_index=payload.suggestion_id,
            )
            break
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    contract.ai_suggestions = suggestions
    flag_modified(contract, "ai_suggestions")
    flag_modified(contract, "change_history")
    write_audit(
        db,
        user=user,
        action_type="contract_suggestion_decision",
        module="contract_review",
        input_summary=f"suggestion={payload.suggestion_id}",
        human_decision=payload.decision,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(contract)
    return _contract_out(contract, db)


@router.post("/{contract_id}/suggestions/preview", response_model=ContractSuggestionsPreview)
def suggestions_preview(
    contract_id: int,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractSuggestionsPreview:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    base_text = contract.raw_text
    suggestions = list(contract.ai_suggestions or [])
    edited_text, applied, blocked = compile_accepted_suggestions(base_text, suggestions)
    accepted = [s for s in suggestions if s.get("decision") in ("accept", "modify")]
    return ContractSuggestionsPreview(
        base_text=base_text,
        edited_text=edited_text,
        diff_blocks=_line_diff(base_text, edited_text),
        applied_count=len(applied),
        blocked_count=len(blocked),
        accepted_count=len(accepted),
        applied=applied,
        blocked=blocked,
    )


@router.post("/{contract_id}/suggestions/apply", response_model=ContractOut)
def suggestions_apply(
    contract_id: int,
    payload: ContractSuggestionsApply,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ContractOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if contract.status == "finalized":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract already finalized")
    base_text = contract.raw_text
    suggestions = list(contract.ai_suggestions or [])
    edited_text, applied, blocked = compile_accepted_suggestions(base_text, suggestions)
    if payload.edited_text.strip() and payload.edited_text != edited_text:
        edited_text = payload.edited_text
    if not applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accepted suggestions could be applied.",
        )
    if blocked and not payload.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(blocked)} suggestion(s) blocked — set force=true to apply partial",
        )
    contract.raw_text = edited_text
    contract.change_history = append_change_entry(
        contract.change_history,
        source="ai_suggestion",
        status="applied",
        before=base_text[:500],
        after=edited_text[:500],
        rationale=f"Applied {len(applied)} suggestion(s) in {payload.change_mode} mode",
        decided_by_id=user.id,
    )
    flag_modified(contract, "change_history")
    write_audit(
        db,
        user=user,
        action_type="contract_suggestions_applied",
        module="contract_review",
        input_summary=f"contract_id={contract_id} applied={len(applied)} mode={payload.change_mode}",
        human_decision="applied",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(contract)
    return _contract_out(contract, db)


@router.get("/{contract_id}/changes", response_model=ContractChangesOut)
def get_changes(
    contract_id: int,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractChangesOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return ContractChangesOut(change_history=contract.change_history or [])


@router.post("/{contract_id}/finalize", response_model=ContractOut)
def finalize_contract(
    contract_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ContractOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    contract.status = "finalized"
    contract.reviewed_by_id = user.id
    contract.reviewed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user=user,
        action_type="contract_finalized",
        module="contract_review",
        input_summary=f"contract_id={contract_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(contract)
    return ContractOut.model_validate(contract)


# ── Prompt-based document editing (track mode) ─────────────────────────────────


@router.post(
    "/{contract_id}/prompt-edit",
    response_model=ContractRevisionOut,
    status_code=status.HTTP_201_CREATED,
)
def prompt_edit(
    contract_id: int,
    payload: PromptEditCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractRevisionOut:
    """Edit the document via a plain-language instruction.

    Produces a *proposed* revision (status="proposed") with a track-mode redline.
    Nothing is applied to the contract until the reviewer explicitly applies it.
    """
    if not payload.instruction.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="instruction is required")
    from app.orchestrator.task_runner import TaskBlockedError
    from app.services.edit_instruction import EditInstructionRejected, assert_edit_instruction_allowed

    try:
        assert_edit_instruction_allowed(payload.instruction)
    except EditInstructionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    base_text = contract.raw_text
    try:
        result = orch_tasks.edit_document(
            base_text,
            payload.instruction,
            selection=payload.selection,
            module="contract_review",
            operation="prompt_edit",
            user_id=user.id,
            db=db,
        )
    except (TaskBlockedError, EditInstructionRejected) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=getattr(exc, "message", str(exc)),
        ) from exc

    from app.services.markdown_tables import normalize_markdown_tables

    edited_text = normalize_markdown_tables(result.edited_text)
    change_summary = (
        normalize_markdown_tables(result.change_summary) if result.change_summary else result.change_summary
    )
    changes = [
        {
            "description": normalize_markdown_tables(c.description),
            "original": c.original,
            "revised": normalize_markdown_tables(c.revised),
        }
        for c in result.changes
    ]

    revision = ContractRevision(
        contract_id=contract.id,
        instruction=payload.instruction,
        selection=payload.selection,
        base_text=base_text,
        edited_text=edited_text,
        change_summary=change_summary,
        changes=changes,
        diff_blocks=_line_diff(base_text, edited_text),
        status="proposed",
        model_version=result.model_version,
        created_by_id=user.id,
    )
    db.add(revision)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="prompt_edit_proposed",
        module="contract_review",
        input_summary=f"contract_id={contract_id} instruction={payload.instruction[:200]}",
        ai_output_summary=(result.change_summary or "")[:500],
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(revision)
    return ContractRevisionOut.model_validate(revision)


@router.get("/{contract_id}/revisions", response_model=list[ContractRevisionSummary])
def list_revisions(
    contract_id: int,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> list[ContractRevisionSummary]:
    rows = (
        db.execute(
            select(ContractRevision)
            .where(ContractRevision.contract_id == contract_id)
            .order_by(ContractRevision.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ContractRevisionSummary.model_validate(r) for r in rows]


@router.get("/{contract_id}/revisions/{revision_id}", response_model=ContractRevisionOut)
def get_revision(
    contract_id: int,
    revision_id: int,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractRevisionOut:
    revision = db.get(ContractRevision, revision_id)
    if revision is None or revision.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    return ContractRevisionOut.model_validate(revision)


@router.post("/{contract_id}/revisions/{revision_id}/apply", response_model=ContractOut)
def apply_revision(
    contract_id: int,
    revision_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ContractOut:
    """Apply a proposed edit — the reviewer-control gate. Requires approve permission."""
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    revision = db.get(ContractRevision, revision_id)
    if revision is None or revision.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    if revision.status != "proposed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Revision already {revision.status}",
        )
    contract.raw_text = revision.edited_text
    revision.status = "applied"
    revision.applied_at = datetime.now(timezone.utc)
    contract.change_history = append_change_entry(
        contract.change_history,
        source="prompt_edit",
        status="applied",
        before=revision.base_text[:500],
        after=revision.edited_text[:500],
        rationale=revision.change_summary,
        decided_by_id=user.id,
    )
    flag_modified(contract, "change_history")
    write_audit(
        db,
        user=user,
        action_type="prompt_edit_applied",
        module="contract_review",
        input_summary=f"contract_id={contract_id} revision_id={revision_id}",
        human_decision="applied",
        model_version=revision.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(contract)
    return _contract_out(contract, db)


@router.post("/{contract_id}/revisions/{revision_id}/discard", response_model=ContractRevisionOut)
def discard_revision(
    contract_id: int,
    revision_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> ContractRevisionOut:
    revision = db.get(ContractRevision, revision_id)
    if revision is None or revision.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    if revision.status == "applied":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot discard an applied revision")
    revision.status = "discarded"
    write_audit(
        db,
        user=user,
        action_type="prompt_edit_discarded",
        module="contract_review",
        input_summary=f"contract_id={contract_id} revision_id={revision_id}",
        human_decision="discarded",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=contract_id,
    )
    db.commit()
    db.refresh(revision)
    return ContractRevisionOut.model_validate(revision)
