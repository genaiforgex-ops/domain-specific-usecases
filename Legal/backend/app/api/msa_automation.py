"""UC-05 MSA / NDA Automation with document versioning."""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import (
    SESSION_COOKIE_NAME,
    client_ip,
    get_current_user,
    session_id,
)
from app.config import settings
from app.core.rbac import Permission
from app.database import SessionLocal, get_db
from app.core.security import decode_access_token
from app.models.comparison import DocumentComparison
from app.models.msa import MSAEmail, MSATracker
from app.models.msa_share import MSAShare
from app.models.msa_prompt_revision import MSAPromptRevision
from app.models.msa_version import MSADocumentVersion
from app.models.negotiation_memory import NegotiationMemory
from app.models.negotiation_task import NegotiationChangeTask
from app.models.playbook import PlaybookClause
from app.models.task import Task
from app.schemas.msa import (
    MSADecideAll,
    MSADecision,
    MSAGmailWatchIn,
    MSAGmailWatchOut,
    MSAIngestEmail,
    MSAOut,
    MSARiskBreakdown,
    MSARunReviewRequest,
    MSASendEmail,
    MSAShareCreate,
    MSAShareOut,
    MSASummary,
    NegotiationMemoryOut,
    ShareableUserOut,
)
from app.models.user import User
from app.schemas.msa_version import (
    DocumentVersionOut,
    MSAHumanEditApply,
    MSAPromptEditApply,
    MSAPromptEditPreview,
    MSAPromptEditRequest,
    MSAPromptRevisionOut,
    MSAPromptRevisionSummary,
    MSADocxOperationOut,
    MSADocxOperationResultOut,
    MSASuggestionsApply,
    MSASuggestionsPreview,
    MSAStartRequest,
    OnlyOfficeConfigOut,
    OnlyOfficeForcesaveOut,
    NegotiationChangeItemOut,
    NegotiationChangesOut,
    NegotiationTaskOut,
    NegotiationTaskUpdate,
)
from app.schemas.task import TaskOut
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.document_parser import DocumentParseError, parse_document, render_text_to_docx, render_text_to_pdf
from app.services.docx_operation_service import apply_operations_to_docx, project_text_after_operations
from app.services.docx_replace_service import apply_replacements_to_docx
from app.services.docx_structure_service import DocumentStructure, extract_structure
from app.services.document_storage import get_document_storage
from app.services.gmail_service import get_gmail_service
from app.services.msa_gmail_ingest_service import add_msa_watch, list_msa_watches, remove_msa_watch
from app.services.msa_prompt_revision_service import get_edit_memory, list_prompt_revisions, operation_to_dict
from app.services.msa_version_service import (
    compare_two_versions,
    create_version,
    get_latest_changes,
    ingest_file_version,
    risk_score_from_suggestions,
    synthesize_suggestions_from_narrative,
)
from app.services.onlyoffice_service import (
    build_editor_config,
    document_key,
    is_office_editable,
    onlyoffice_enabled,
    sign_config,
    trigger_forcesave,
)
from app.services.suggestion_service import (
    clause_to_suggestion_dict,
    compile_accepted_suggestions,
    filter_actionable_suggestions,
    line_diff,
    replacement_pairs,
)
from app.services.review_workspace_service import (
    append_change_entry,
    format_regulatory_context,
    load_playbook_context,
    normalize_findings,
)
from app.services.msa_risk_service import compute_risk_breakdown
from app.services.negotiation_memory_service import (
    list_memory,
    memory_snippets,
    record_decision,
    record_edit_summary,
    record_guidelines,
)
from app.services import template_service
from app.services.msa_access import (
    ACCESS_EDIT,
    ACCESS_OWNER,
    ACCESS_VIEW,
    access_level_for,
    can_apply_msa_changes,
    is_msa_owner,
    load_tracker_with_access,
    require_msa_module,
    require_msa_owner,
)

logger = logging.getLogger("legalos.msa")

router = APIRouter(prefix="/api/msa", tags=["msa-automation"])


def _share_out(share: MSAShare, db: Session) -> MSAShareOut:
    recipient = db.get(User, share.user_id)
    return MSAShareOut(
        id=share.id,
        tracker_id=share.tracker_id,
        user_id=share.user_id,
        shared_by_id=share.shared_by_id,
        access_level=share.access_level,
        shared_at=share.shared_at,
        user_email=recipient.email if recipient else None,
        user_full_name=recipient.full_name if recipient else None,
    )


def _document_text_for_tracker(db: Session, tracker: MSATracker) -> str:
    parent = _latest_legal_version(db, tracker.id)
    if parent and parent.extracted_text:
        return parent.extracted_text
    return tracker.original_text or ""


def _risk_breakdown_out(db: Session, tracker: MSATracker) -> MSARiskBreakdown:
    doc_text = _document_text_for_tracker(db, tracker)
    raw = compute_risk_breakdown(
        tracker.ai_suggestions,
        guidelines=tracker.review_guidelines,
        document_text=doc_text,
    )
    return MSARiskBreakdown(**raw)


def _merge_suggestions_on_rereview(
    old: list[dict],
    new: list[dict],
    document_text: str,
) -> list[dict]:
    """Replace pending suggestions; preserve human decisions when original text remains."""
    text_lc = document_text.lower()
    decisions_by_original: dict[str, dict] = {}
    for s in old:
        decision = s.get("decision")
        if decision not in ("accept", "reject", "modify"):
            continue
        orig = (s.get("original_text") or "").strip()
        if orig and orig.lower() in text_lc:
            decisions_by_original[orig.lower()] = {
                "decision": decision,
                "reviewer_edit": s.get("reviewer_edit"),
            }
    merged: list[dict] = []
    for s in new:
        ns = dict(s)
        orig = (ns.get("original_text") or "").strip().lower()
        if orig and orig in decisions_by_original:
            ns.update(decisions_by_original[orig])
        merged.append(ns)
    return merged


def _to_out(
    t: MSATracker,
    *,
    user: User | None = None,
    db: Session | None = None,
    include_shares: bool = False,
) -> MSAOut:
    base = MSAOut.model_validate(t)
    data = base.model_dump()
    if user is not None and db is not None:
        data["my_access_level"] = access_level_for(user, t.id, db)
    if db is not None:
        data["risk_breakdown"] = _risk_breakdown_out(db, t)
    if include_shares and db is not None:
        shares = db.execute(select(MSAShare).where(MSAShare.tracker_id == t.id)).scalars().all()
        data["shares"] = [_share_out(s, db) for s in shares]
    return MSAOut(**data)


def _summary_out(t: MSATracker, user: User, db: Session) -> MSASummary:
    return MSASummary(
        id=t.id,
        vendor_name=t.vendor_name,
        contract_type=t.contract_type,
        status=t.status,
        risk_score=t.risk_score,
        updated_at=t.updated_at,
        my_access_level=access_level_for(user, t.id, db),
    )


def _version_out(v: MSADocumentVersion) -> DocumentVersionOut:
    out = DocumentVersionOut.model_validate(v)
    if v.storage_key:
        out.download_url = get_document_storage().presigned_url(v.storage_key)
    return out


def _ground_truth_suggestions(text: str, guidelines: str | None) -> list[dict]:
    """Turn simple ground-truth lines into deterministic review findings.

    Supports plain lines such as "JFPSL" or "Jio Finance Platform and Service
    Limited". If the exact text is absent, the reviewer sees a high-risk item.
    """
    if not guidelines or not guidelines.strip():
        return []
    findings: list[dict] = []
    text_lc = text.lower()
    for i, raw in enumerate(guidelines.splitlines()):
        expected = raw.strip().strip("-* ")
        if not expected:
            continue
        if expected.lower() in text_lc:
            continue
        findings.append(
            {
                "order_index": 9000 + i,
                "heading": f"Ground truth check: {expected[:80]}",
                "clause_text": expected,
                "risk_flag": "high",
                "confidence": 0.95,
                "rationale": "This exact ground-truth term was provided by the reviewer but was not found in the document.",
                "ai_suggestion": f"Verify the document uses the exact required wording: {expected}",
                "original_text": None,
                "proposed_text": expected,
                "category": "policy",
                "decision": "pending",
            }
        )
    return findings


def _instruction_with_guidelines(instruction: str, guidelines: str | None) -> str:
    if not guidelines or not guidelines.strip():
        return instruction
    return (
        instruction.strip()
        + "\n\nGround truth / reviewer guidelines that must be preserved:\n"
        + guidelines.strip()
    )


@router.get("", response_model=list[MSASummary])
def list_trackers(
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[MSASummary]:
    if is_msa_owner(user):
        rows = db.execute(select(MSATracker).order_by(MSATracker.updated_at.desc())).scalars().all()
    else:
        rows = db.execute(
            select(MSATracker)
            .join(MSAShare, MSAShare.tracker_id == MSATracker.id)
            .where(MSAShare.user_id == user.id)
            .order_by(MSATracker.updated_at.desc())
        ).scalars().all()
    return [_summary_out(t, user, db) for t in rows]


@router.get("/gmail/watches", response_model=list[MSAGmailWatchOut])
def get_msa_gmail_watches(
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[MSAGmailWatchOut]:
    watches = list_msa_watches(db, user)
    return [
        MSAGmailWatchOut(
            thread_id=w.get("thread_id", ""),
            tracker_id=w.get("tracker_id"),
            subject=w.get("subject"),
            vendor_email=w.get("vendor_email"),
            added_at=w.get("added_at"),
        )
        for w in watches
        if isinstance(w, dict) and w.get("thread_id")
    ]


@router.post("/gmail/watch", response_model=list[MSAGmailWatchOut])
def watch_msa_gmail_thread(
    payload: MSAGmailWatchIn,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> list[MSAGmailWatchOut]:
    svc = get_gmail_service()
    if not settings.gmail_enabled or not svc.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail is not configured or enabled",
        )
    watches = add_msa_watch(
        db,
        user,
        thread_id=payload.thread_id,
        tracker_id=None,
        subject=payload.subject,
        vendor_email=payload.vendor_email,
    )
    return [
        MSAGmailWatchOut(
            thread_id=w.get("thread_id", ""),
            tracker_id=w.get("tracker_id"),
            subject=w.get("subject"),
            vendor_email=w.get("vendor_email"),
            added_at=w.get("added_at"),
        )
        for w in watches
        if isinstance(w, dict) and w.get("thread_id")
    ]


@router.post("/{tracker_id}/gmail/watch", response_model=MSAOut)
def link_msa_gmail_thread(
    tracker_id: int,
    payload: MSAGmailWatchIn,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    svc = get_gmail_service()
    if not settings.gmail_enabled or not svc.is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail is not configured or enabled",
        )
    tracker.gmail_thread_id = payload.thread_id
    tracker.gmail_auto_ingest = True
    add_msa_watch(
        db,
        user,
        thread_id=payload.thread_id,
        tracker_id=tracker.id,
        subject=payload.subject or f"{tracker.vendor_name} negotiation",
        vendor_email=payload.vendor_email or tracker.vendor_email,
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


@router.delete("/{tracker_id}/gmail/watch", response_model=MSAOut)
def unlink_msa_gmail_thread(
    tracker_id: int,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    thread_id = tracker.gmail_thread_id
    tracker.gmail_auto_ingest = False
    if thread_id:
        remove_msa_watch(db, user, thread_id)
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


def _do_start_negotiation(
    payload: MSAStartRequest,
    request: Request,
    user: User,
    db: Session,
    *,
    base_file_bytes: bytes | None = None,
    base_filename: str | None = None,
    base_mime_type: str | None = None,
) -> MSAOut:
    base_text = payload.base_text
    if payload.template_id:
        tmpl = template_service.get_template(db, payload.template_id)
        if tmpl is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        base_text = base_text or tmpl.template_text
    if not base_text or not base_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide template_id or base_text",
        )

    suggestions: list[dict] = []
    result_risk: float | None = None
    result_model: str | None = None
    tracker_status = "under_review"

    if payload.skip_ai_review:
        tracker_status = "draft"
    else:
        ctx = load_playbook_context(db, payload.contract_type)
        reg_block = format_regulatory_context(ctx.regulatory_snippets)
        review_text = base_text
        if reg_block:
            review_text = f"{reg_block}\n\n---\n\n{base_text}"
        result = orch_tasks.review_contract(
            review_text,
            ctx.clauses,
            contract_type=payload.contract_type,
            module="msa_automation",
            operation="review_contract",
            user_id=user.id,
            db=db,
        )
        suggestions = filter_actionable_suggestions(
            normalize_findings(result.clauses, ctx.clauses, ctx.clause_bank)
        )
        suggestions.extend(_ground_truth_suggestions(base_text, payload.review_guidelines))
        result_risk = risk_score_from_suggestions(suggestions) if suggestions else result.risk_score
        result_model = result.model_version

    tracker = MSATracker(
        vendor_name=payload.vendor_name,
        vendor_email=str(payload.vendor_email),
        contract_type=payload.contract_type,
        deal_reference=payload.deal_reference,
        status=tracker_status,
        risk_score=result_risk,
        current_version=0,
        original_text=base_text,
        ai_suggestions=suggestions,
        template_id=payload.template_id,
        assigned_to_id=user.id,
        review_guidelines=payload.review_guidelines,
    )
    db.add(tracker)
    db.flush()
    if payload.review_guidelines:
        record_guidelines(db, tracker.id, payload.review_guidelines, user.id)

    storage_key: str | None = None
    sha: str | None = None
    if base_file_bytes is not None and base_filename:
        storage = get_document_storage()
        storage_key, sha = storage.upload(
            base_file_bytes, base_filename, base_mime_type or "application/octet-stream"
        )

    create_version(
        db,
        tracker,
        source="legal_base",
        extracted_text=base_text,
        user=user,
        filename=base_filename or "base.txt",
        mime_type=base_mime_type,
        storage_key=storage_key,
        sha256=sha,
        run_compare=False,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    write_audit(
        db,
        user=user,
        action_type="msa_started",
        module="msa_automation",
        input_summary=f"vendor={payload.vendor_name}",
        ai_output_summary=f"risk={result_risk}" if result_risk is not None else "draft",
        model_version=result_model,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


@router.post("/start", response_model=MSAOut, status_code=status.HTTP_201_CREATED)
def start_negotiation(
    payload: MSAStartRequest,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    return _do_start_negotiation(payload, request, user, db)


@router.post("/start/upload", response_model=MSAOut, status_code=status.HTTP_201_CREATED)
async def start_negotiation_upload(
    request: Request,
    vendor_name: str = Form(...),
    vendor_email: str = Form(...),
    contract_type: str = Form("MSA"),
    deal_reference: str | None = Form(None),
    template_id: int | None = Form(None),
    review_guidelines: str | None = Form(None),
    skip_ai_review: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    filename = file.filename or "upload.txt"
    mime_type = file.content_type
    try:
        text = __import__(
            "app.services.document_parser", fromlist=["parse_document"]
        ).parse_document(data, filename, mime_type)
    except DocumentParseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    try:
        req = MSAStartRequest(
            vendor_name=vendor_name,
            vendor_email=vendor_email,
            contract_type=contract_type,
            deal_reference=deal_reference,
            template_id=template_id,
            base_text=text,
            review_guidelines=review_guidelines,
            skip_ai_review=skip_ai_review,
        )
    except ValidationError as e:
        detail = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e
    return _do_start_negotiation(
        req,
        request,
        user,
        db,
        base_file_bytes=data,
        base_filename=filename,
        base_mime_type=mime_type,
    )


@router.post("/ingest", response_model=MSAOut, status_code=status.HTTP_201_CREATED)
def ingest_email(
    payload: MSAIngestEmail,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    """Legacy Gmail-style intake — creates new tracker + v1."""
    req = MSAStartRequest(
        vendor_name=payload.vendor_name,
        vendor_email=payload.vendor_email,
        contract_type=payload.contract_type,
        deal_reference=payload.deal_reference,
        base_text=payload.attachment_text,
    )
    tracker_out = start_negotiation(req, request, user, db)
    tracker = db.get(MSATracker, tracker_out.id)
    if tracker:
        db.add(
            MSAEmail(
                tracker_id=tracker.id,
                direction="in",
                from_addr=str(payload.vendor_email),
                to_addr="legal@jfpsl.in",
                subject=payload.subject,
                body=payload.body,
                attachment_name=payload.attachment_name,
            )
        )
        db.commit()
        db.refresh(tracker)
        return _to_out(tracker, user=user, db=db)
    return tracker_out


def _apply_ai_review(
    tracker: MSATracker,
    base_text: str,
    review_guidelines: str | None,
    user: User,
    request: Request,
    db: Session,
    *,
    merge_from: list[dict] | None = None,
) -> None:
    effective_guidelines = review_guidelines if review_guidelines is not None else tracker.review_guidelines
    snippets = memory_snippets(db, tracker.id)
    if snippets:
        mem_block = "\n".join(snippets)
        effective_guidelines = (effective_guidelines or "") + "\n\nNegotiation memory:\n" + mem_block

    ctx = load_playbook_context(db, tracker.contract_type)
    reg_block = format_regulatory_context(ctx.regulatory_snippets)
    review_text = base_text
    if reg_block:
        review_text = f"{reg_block}\n\n---\n\n{base_text}"
    result = orch_tasks.review_contract(
        review_text,
        ctx.clauses,
        contract_type=tracker.contract_type,
        module="msa_automation",
        operation="review_contract",
        user_id=user.id,
        db=db,
    )
    suggestions = filter_actionable_suggestions(
        normalize_findings(result.clauses, ctx.clauses, ctx.clause_bank)
    )
    suggestions.extend(_ground_truth_suggestions(base_text, effective_guidelines))
    if merge_from:
        suggestions = _merge_suggestions_on_rereview(merge_from, suggestions, base_text)
    tracker.ai_suggestions = suggestions
    tracker.risk_score = (
        risk_score_from_suggestions(suggestions) if suggestions else result.risk_score
    )
    if tracker.status == "draft":
        tracker.status = "under_review"
    write_audit(
        db,
        user=user,
        action_type="msa_ai_review_run",
        module="msa_automation",
        input_summary=f"tracker={tracker.id}",
        ai_output_summary=f"risk={tracker.risk_score}",
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
    )


@router.post("/{tracker_id}/run-review", response_model=MSAOut)
def run_ai_review(
    tracker_id: int,
    request: Request,
    payload: MSARunReviewRequest | None = None,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    body = payload or MSARunReviewRequest()
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if tracker.status == "executed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Negotiation already executed")
    if body.review_guidelines is not None:
        tracker.review_guidelines = body.review_guidelines
        record_guidelines(db, tracker_id, body.review_guidelines, user.id)
    if body.version_id is not None:
        version = db.get(MSADocumentVersion, body.version_id)
        if version is None or version.tracker_id != tracker_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
        base_text = version.extracted_text or ""
    else:
        parent = _latest_legal_version(db, tracker_id)
        base_text = (parent.extracted_text if parent else None) or tracker.original_text or ""
    if not base_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No document text to review")
    old_suggestions = list(tracker.ai_suggestions or [])
    _apply_ai_review(
        tracker,
        base_text,
        tracker.review_guidelines,
        user,
        request,
        db,
        merge_from=old_suggestions if old_suggestions else None,
    )
    db.commit()
    db.refresh(tracker)
    include_shares = level == ACCESS_OWNER
    return _to_out(tracker, user=user, db=db, include_shares=include_shares)


@router.get("/shareable-users", response_model=list[ShareableUserOut])
def list_shareable_users(
    q: str = "",
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> list[ShareableUserOut]:
    stmt = select(User).where(User.is_active.is_(True))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            (User.email.ilike(like)) | (User.full_name.ilike(like))
        )
    rows = db.execute(stmt.order_by(User.full_name).limit(200)).scalars().all()
    return [
        ShareableUserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role)
        for u in rows
        if u.id != user.id
    ]


@router.get("/{tracker_id}/shares", response_model=list[MSAShareOut])
def list_shares(
    tracker_id: int,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> list[MSAShareOut]:
    if db.get(MSATracker, tracker_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found")
    shares = db.execute(select(MSAShare).where(MSAShare.tracker_id == tracker_id)).scalars().all()
    return [_share_out(s, db) for s in shares]


@router.post("/{tracker_id}/shares", response_model=MSAShareOut, status_code=status.HTTP_201_CREATED)
def create_share(
    tracker_id: int,
    payload: MSAShareCreate,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAShareOut:
    if payload.access_level not in {ACCESS_VIEW, ACCESS_EDIT}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="access_level must be view or edit")
    tracker = db.get(MSATracker, tracker_id)
    if tracker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found")
    recipient = db.get(User, payload.user_id)
    if recipient is None or not recipient.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = db.execute(
        select(MSAShare).where(MSAShare.tracker_id == tracker_id, MSAShare.user_id == payload.user_id)
    ).scalar_one_or_none()
    if existing:
        existing.access_level = payload.access_level
        existing.shared_by_id = user.id
        share = existing
    else:
        share = MSAShare(
            tracker_id=tracker_id,
            user_id=payload.user_id,
            shared_by_id=user.id,
            access_level=payload.access_level,
        )
        db.add(share)
        from app.services.notify_hooks import notify_msa_shared

        notify_msa_shared(
            db,
            recipient,
            user.full_name or "A colleague",
            tracker.vendor_name or "a vendor",
            tracker_id,
            payload.access_level,
        )
    write_audit(
        db,
        user=user,
        action_type="msa_shared",
        module="msa_automation",
        input_summary=f"tracker={tracker_id} user={payload.user_id} level={payload.access_level}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
    )
    db.commit()
    db.refresh(share)
    return _share_out(share, db)


@router.delete("/{tracker_id}/shares/{share_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    tracker_id: int,
    share_user_id: int,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> None:
    share = db.execute(
        select(MSAShare).where(MSAShare.tracker_id == tracker_id, MSAShare.user_id == share_user_id)
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    db.delete(share)
    write_audit(
        db,
        user=user,
        action_type="msa_share_revoked",
        module="msa_automation",
        input_summary=f"tracker={tracker_id} user={share_user_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
    )
    db.commit()


@router.get("/{tracker_id}", response_model=MSAOut)
def get_tracker(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    include_shares = level == ACCESS_OWNER
    tracker = db.execute(
        select(MSATracker)
        .where(MSATracker.id == tracker_id)
        .options(joinedload(MSATracker.emails))
    ).unique().scalar_one()
    return _to_out(tracker, user=user, db=db, include_shares=include_shares)


@router.get("/{tracker_id}/versions", response_model=list[DocumentVersionOut])
def list_versions(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[DocumentVersionOut]:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    rows = db.execute(
        select(MSADocumentVersion)
        .where(MSADocumentVersion.tracker_id == tracker_id)
        .order_by(MSADocumentVersion.version_number)
    ).scalars().all()
    return [_version_out(v) for v in rows]


@router.get("/{tracker_id}/versions/{version_id}/text")
def get_version_text(
    tracker_id: int,
    version_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> dict:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    version = db.get(MSADocumentVersion, version_id)
    if version is None or version.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return {"version_id": version.id, "extracted_text": version.extracted_text or ""}


@router.post("/{tracker_id}/versions", response_model=DocumentVersionOut, status_code=status.HTTP_201_CREATED)
async def upload_version(
    tracker_id: int,
    request: Request,
    source: str = Form("vendor_return"),
    parent_version_id: int | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> DocumentVersionOut:
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_OWNER)
    if source not in ("vendor_return", "legal_redline", "legal_base"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    try:
        version, _ = ingest_file_version(
            db,
            tracker,
            data,
            file.filename or "upload.txt",
            file.content_type,
            source=source,
            user=user,
            parent_version_id=parent_version_id,
            ip_address=client_ip(request),
            session_id=session_id(request),
        )
        db.commit()
        db.refresh(version)
        return _version_out(version)
    except DocumentParseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _line_diff(before: str, after: str) -> list[dict]:
    """Line-level redline blocks for track-mode rendering (matches DiffView)."""
    return line_diff(before, after)


def _ensure_version_structure(version: MSADocumentVersion) -> dict | None:
    if version.structure_snapshot:
        return version.structure_snapshot
    if not _is_docx_parent(version) or not version.storage_key:
        return None
    try:
        data = get_document_storage().download(version.storage_key)
        structure = extract_structure(data)
        version.structure_snapshot = structure.to_dict()
        version.structure_hash = structure.structure_hash
        return version.structure_snapshot
    except Exception as exc:
        logger.warning("DOCX structure extraction failed for version %s: %s", version.id, exc)
        return None


def _operations_out(ops: list | None) -> list[MSADocxOperationOut]:
    return [
        MSADocxOperationOut(
            op_type=op.get("op_type", ""),
            anchor_id=op.get("anchor_id"),
            after_anchor_id=op.get("after_anchor_id"),
            target_text=op.get("target_text"),
            content=op.get("content"),
            description=op.get("description", ""),
            confidence=float(op.get("confidence", 0.8)),
        )
        for op in (ops or [])
    ]


def _operation_results_out(results: list | None) -> list[MSADocxOperationResultOut]:
    return [
        MSADocxOperationResultOut(
            op_index=int(r.get("op_index", 0)),
            op_type=r.get("op_type", ""),
            description=r.get("description", ""),
            status=r.get("status", ""),
            message=r.get("message", ""),
        )
        for r in (results or [])
    ]


def _revision_to_out(revision: MSAPromptRevision) -> MSAPromptRevisionOut:
    return MSAPromptRevisionOut(
        id=revision.id,
        tracker_id=revision.tracker_id,
        base_version_id=revision.base_version_id,
        instruction=revision.instruction,
        selection=revision.selection,
        base_text=revision.base_text,
        edited_text=revision.edited_text,
        change_summary=revision.change_summary,
        operations=_operations_out(revision.operations),
        operation_results=_operation_results_out(revision.operation_results),
        structure_hash=revision.structure_hash,
        edit_mode=revision.edit_mode,
        diff_blocks=revision.diff_blocks or [],
        status=revision.status,
        model_version=revision.model_version,
        resulting_version_id=revision.resulting_version_id,
        created_at=revision.created_at,
        applied_at=revision.applied_at,
    )


def _is_docx_parent(parent: MSADocumentVersion) -> bool:
    return is_office_editable(parent.filename, parent.mime_type)


def _create_legal_redline_from_bytes(
    db: Session,
    tracker: MSATracker,
    parent: MSADocumentVersion,
    file_bytes: bytes,
    extracted_text: str,
    user: User,
    request: Request,
    *,
    audit_action: str,
    audit_summary: str,
    structure_snapshot: dict | None = None,
    structure_hash: str | None = None,
) -> MSAOut:
    next_version = tracker.current_version + 1
    base_name = f"{tracker.vendor_name}_v{next_version}_legal_edit"
    parent_name = (parent.filename or "").lower()
    if parent_name.endswith(".docx") or "word" in (parent.mime_type or "").lower():
        filename = f"{base_name}.docx"
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        filename = parent.filename or f"{base_name}.docx"
        mime_type = parent.mime_type or "application/octet-stream"
    storage_key, sha = get_document_storage().upload(file_bytes, filename, mime_type)
    version, _ = create_version(
        db,
        tracker,
        source="legal_redline",
        extracted_text=extracted_text,
        user=user,
        filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        sha256=sha,
        parent_version_id=parent.id,
        structure_snapshot=structure_snapshot,
        structure_hash=structure_hash,
        run_compare=True,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    if tracker.status != "executed":
        tracker.status = "redlined"
    record_edit_summary(
        db,
        tracker.id,
        audit_summary,
        user.id,
        version_id=version.id,
    )
    write_audit(
        db,
        user=user,
        action_type=audit_action,
        module="msa_automation",
        input_summary=audit_summary,
        human_decision="applied",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
        extra={"version_number": version.version_number},
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


def _render_and_store_legal_version(
    tracker: MSATracker,
    parent: MSADocumentVersion,
    edited_text: str,
) -> tuple[str, str, str | None, str | None]:
    """Render edited text to DOCX/PDF and upload. Returns filename, mime_type, storage_key, sha."""
    next_version = tracker.current_version + 1
    base_name = f"{tracker.vendor_name}_v{next_version}_legal_edit"
    title = f"{tracker.vendor_name} - v{next_version}"
    storage_key: str | None = None
    sha: str | None = None
    parent_name = (parent.filename or "").lower()
    parent_mime = (parent.mime_type or "").lower()
    if parent_name.endswith(".docx") or "word" in parent_mime or "docx" in parent_mime:
        docx_bytes = render_text_to_docx(edited_text, title=title)
        if docx_bytes is not None:
            filename = f"{base_name}.docx"
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            storage_key, sha = get_document_storage().upload(docx_bytes, filename, mime_type)
        else:
            filename = f"{base_name}.txt"
            mime_type = "text/plain"
            storage_key, sha = get_document_storage().upload(
                edited_text.encode("utf-8"), filename, mime_type
            )
    else:
        pdf_bytes = render_text_to_pdf(edited_text, title=title)
        if pdf_bytes is not None:
            filename = f"{base_name}.pdf"
            mime_type = "application/pdf"
            storage_key, sha = get_document_storage().upload(pdf_bytes, filename, mime_type)
        else:
            filename = f"{base_name}.txt"
            mime_type = "text/plain"
            storage_key, sha = get_document_storage().upload(
                edited_text.encode("utf-8"), filename, mime_type
            )
    return filename, mime_type, storage_key, sha


def _create_legal_redline_from_text(
    db: Session,
    tracker: MSATracker,
    parent: MSADocumentVersion,
    edited_text: str,
    user: User,
    request: Request,
    *,
    audit_action: str,
    audit_summary: str,
) -> MSAOut:
    filename, mime_type, storage_key, sha = _render_and_store_legal_version(
        tracker, parent, edited_text
    )
    version, _ = create_version(
        db,
        tracker,
        source="legal_redline",
        extracted_text=edited_text,
        user=user,
        filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        sha256=sha,
        parent_version_id=parent.id,
        run_compare=True,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    if tracker.status != "executed":
        tracker.status = "redlined"
    record_edit_summary(
        db,
        tracker.id,
        audit_summary,
        user.id,
        version_id=version.id,
    )
    write_audit(
        db,
        user=user,
        action_type=audit_action,
        module="msa_automation",
        input_summary=audit_summary,
        human_decision="applied",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
        extra={"version_number": version.version_number},
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


def _latest_legal_version(db: Session, tracker_id: int) -> MSADocumentVersion | None:
    """Most recent legal-authored version (redline preferred, else base)."""
    return db.execute(
        select(MSADocumentVersion)
        .where(
            MSADocumentVersion.tracker_id == tracker_id,
            MSADocumentVersion.source.in_(["legal_redline", "legal_base"]),
        )
        .order_by(MSADocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.post("/{tracker_id}/prompt-edit", response_model=MSAPromptEditPreview, status_code=status.HTTP_201_CREATED)
def prompt_edit_preview(
    tracker_id: int,
    payload: MSAPromptEditRequest,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAPromptEditPreview:
    """Edit the working document via a plain-language instruction.

    For DOCX files, plans structured operations against document parts and
    persists a proposed revision. Text sources use the legacy full-text path.
    """
    if not payload.instruction.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="instruction is required")
    from app.orchestrator.task_runner import TaskBlockedError
    from app.services.edit_instruction import (
        EditInstructionRejected,
        assert_edit_instruction_allowed,
    )

    try:
        assert_edit_instruction_allowed(payload.instruction)
    except EditInstructionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if level == ACCESS_VIEW:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit access required")

    if payload.base_version_id is not None:
        base_version = db.get(MSADocumentVersion, payload.base_version_id)
        if base_version is None or base_version.tracker_id != tracker_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    else:
        base_version = _latest_legal_version(db, tracker_id)
    if base_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No document version available to edit",
        )

    base_text = base_version.extracted_text or ""
    effective_instruction = _instruction_with_guidelines(
        payload.instruction,
        payload.review_guidelines or tracker.review_guidelines,
    )
    edit_memory = get_edit_memory(db, tracker_id)

    operations_out: list[MSADocxOperationOut] = []
    operation_results_out: list[MSADocxOperationResultOut] = []
    changes_out: list[dict] = []
    edit_mode = "text"
    edited_text = base_text
    change_summary: str | None = None
    structure_hash: str | None = base_version.structure_hash
    operations_json: list[dict] | None = None
    model_version: str | None = None
    ai_fallback = False

    structure_dict = _ensure_version_structure(base_version)
    is_docx = _is_docx_parent(base_version)
    try:
        if is_docx and structure_dict:
            logger.info(
                "MSA prompt-edit tracker=%s v=%s backend=%s mode=docx_operations parts=%d text_len=%d",
                tracker_id,
                base_version.version_number,
                settings.ai_backend,
                len(structure_dict.get("parts", [])),
                len(base_text),
            )
            plan = orch_tasks.plan_docx_operations(
                structure_dict,
                effective_instruction,
                selection=payload.selection,
                edit_memory=edit_memory or None,
                full_text=base_text,
                module="msa_automation",
                operation="prompt_edit",
                user_id=user.id,
                db=db,
            )
            operations_json = [operation_to_dict(op) for op in plan.operations]
            operations_out = [
                MSADocxOperationOut(
                    op_type=op.op_type,
                    anchor_id=op.anchor_id,
                    after_anchor_id=op.after_anchor_id,
                    target_text=op.target_text,
                    content=op.content,
                    description=op.description,
                    confidence=op.confidence,
                )
                for op in plan.operations
            ]
            structure = DocumentStructure.from_dict(structure_dict)
            edited_text = project_text_after_operations(structure, operations_json)
            change_summary = plan.change_summary
            model_version = plan.model_version
            ai_fallback = getattr(plan, "used_fallback", False)
            edit_mode = "docx_operations"
            structure_hash = structure.structure_hash
            changes_out = [
                {
                    "description": op.description,
                    "original": op.target_text or "",
                    "revised": op.content or "",
                }
                for op in plan.operations
            ]
        else:
            logger.info(
                "MSA prompt-edit tracker=%s v=%s backend=%s mode=text docx=%s structure=%s text_len=%d",
                tracker_id,
                base_version.version_number,
                settings.ai_backend,
                is_docx,
                bool(structure_dict),
                len(base_text),
            )
            result = orch_tasks.edit_document(
                base_text,
                effective_instruction,
                selection=payload.selection,
                module="msa_automation",
                operation="prompt_edit",
                user_id=user.id,
                db=db,
            )
            edited_text = result.edited_text
            change_summary = result.change_summary
            model_version = result.model_version
            changes_out = [
                {"description": c.description, "original": c.original, "revised": c.revised}
                for c in result.changes
            ]
    except (TaskBlockedError, EditInstructionRejected) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=getattr(exc, "message", str(exc)),
        ) from exc

    from app.services.markdown_tables import normalize_markdown_tables

    edited_text = normalize_markdown_tables(edited_text)
    if change_summary:
        change_summary = normalize_markdown_tables(change_summary)
    if operations_json:
        for op in operations_json:
            if op.get("content"):
                op["content"] = normalize_markdown_tables(op["content"])
            if op.get("description"):
                op["description"] = normalize_markdown_tables(op["description"])
        operations_out = [
            MSADocxOperationOut(
                op_type=op["op_type"],
                anchor_id=op.get("anchor_id"),
                after_anchor_id=op.get("after_anchor_id"),
                target_text=op.get("target_text"),
                content=op.get("content"),
                description=op.get("description") or "",
                confidence=float(op.get("confidence") or 0.8),
            )
            for op in operations_json
        ]
        changes_out = [
            {
                "description": op.description,
                "original": op.target_text or "",
                "revised": op.content or "",
            }
            for op in operations_out
        ]
    else:
        changes_out = [
            {
                "description": normalize_markdown_tables(c.get("description") or ""),
                "original": c.get("original") or "",
                "revised": normalize_markdown_tables(c.get("revised") or ""),
            }
            for c in changes_out
        ]

    # Make it explicit in the logs whether real AI produced this edit or it
    # degraded to the deterministic stub (e.g. missing API key in the cluster).
    logger.info(
        "MSA prompt-edit AI done: tracker=%s mode=%s model_version=%s ai_fallback=%s changes=%d",
        tracker_id,
        edit_mode,
        model_version,
        ai_fallback,
        len(changes_out),
    )

    diff_blocks = _line_diff(base_text, edited_text)
    revision = MSAPromptRevision(
        tracker_id=tracker_id,
        base_version_id=base_version.id,
        instruction=payload.instruction,
        selection=payload.selection,
        base_text=base_text,
        edited_text=edited_text,
        change_summary=change_summary,
        operations=operations_json,
        structure_hash=structure_hash,
        edit_mode=edit_mode,
        diff_blocks=diff_blocks,
        status="proposed",
        model_version=model_version,
        created_by_id=user.id,
    )
    db.add(revision)
    db.flush()

    write_audit(
        db,
        user=user,
        action_type="msa_prompt_edit_proposed",
        module="msa_automation",
        input_summary=f"tracker={tracker_id} v={base_version.version_number} instruction={payload.instruction[:200]}",
        ai_output_summary=(change_summary or "")[:500],
        model_version=model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
        extra={"revision_id": revision.id, "edit_mode": edit_mode},
    )
    db.commit()

    return MSAPromptEditPreview(
        revision_id=revision.id,
        base_version_id=base_version.id,
        base_version_number=base_version.version_number,
        base_text=base_text,
        edited_text=edited_text,
        change_summary=change_summary,
        changes=changes_out,
        operations=operations_out,
        operation_results=operation_results_out,
        edit_mode=edit_mode,
        structure_hash=structure_hash,
        diff_blocks=diff_blocks,
        model_version=model_version,
        ai_fallback=ai_fallback,
    )


@router.post("/{tracker_id}/prompt-edit/apply", response_model=MSAOut)
def prompt_edit_apply(
    tracker_id: int,
    payload: MSAPromptEditApply,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    """Apply a proposed prompt edit as a new legal redline version."""
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    if tracker.status == "executed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Negotiation already executed")

    revision: MSAPromptRevision | None = None
    if payload.revision_id is not None:
        revision = db.get(MSAPromptRevision, payload.revision_id)
        if revision is None or revision.tracker_id != tracker_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
        if revision.status != "proposed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revision already {revision.status}",
            )
        parent = db.get(MSADocumentVersion, revision.base_version_id)
    else:
        if not payload.edited_text.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="edited_text is required")
        parent = db.get(MSADocumentVersion, payload.parent_version_id)

    if parent is None or parent.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent version not found")

    if (
        revision
        and revision.edit_mode == "docx_operations"
        and _is_docx_parent(parent)
        and parent.storage_key
    ):
        # Allow the reviewer to curate planned ops (wording / drop ops) before apply.
        if payload.operations is not None:
            curated = [
                {
                    "op_type": op.op_type,
                    "anchor_id": op.anchor_id,
                    "after_anchor_id": op.after_anchor_id,
                    "target_text": op.target_text,
                    "content": op.content,
                    "description": op.description,
                    "confidence": op.confidence,
                }
                for op in payload.operations
            ]
            if not curated:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one operation is required to apply",
                )
            revision.operations = curated
            structure_for_project = _ensure_version_structure(parent)
            if structure_for_project:
                try:
                    structure_obj = DocumentStructure.from_dict(structure_for_project)
                    revision.edited_text = project_text_after_operations(
                        structure_obj, curated
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Could not reproject text after curated ops tracker=%s: %s",
                        tracker_id,
                        exc,
                    )

        structure_dict = _ensure_version_structure(parent)
        if not structure_dict or not revision.operations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="DOCX structure or operations missing for this revision",
            )
        parent_bytes = get_document_storage().download(parent.storage_key)
        structure = DocumentStructure.from_dict(structure_dict)
        # When track-changes is on, attribute AI edits to a distinct author so
        # they render as a native redline (w:ins/w:del) the vendor can review.
        ai_author = None
        if settings.onlyoffice_force_track_changes:
            ai_author = user.full_name
        apply_result = apply_operations_to_docx(
            parent_bytes, structure, revision.operations, author=ai_author
        )
        if apply_result.docx_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not apply DOCX operations",
            )
        revision.operation_results = [
            {
                "op_index": r.op_index,
                "op_type": r.op_type,
                "description": r.description,
                "status": r.status,
                "message": r.message,
            }
            for r in apply_result.results
        ]
        try:
            extracted = parse_document(
                apply_result.docx_bytes,
                parent.filename or "edit.docx",
                parent.mime_type,
            )
        except DocumentParseError:
            extracted = apply_result.projected_text or revision.edited_text
        new_structure = extract_structure(apply_result.docx_bytes)
        out = _create_legal_redline_from_bytes(
            db,
            tracker,
            parent,
            apply_result.docx_bytes,
            extracted,
            user,
            request,
            audit_action="msa_prompt_edit_applied",
            audit_summary=f"tracker={tracker_id} v={tracker.current_version} instruction={revision.instruction[:200]}",
            structure_snapshot=new_structure.to_dict(),
            structure_hash=new_structure.structure_hash,
        )
        latest_version = db.execute(
            select(MSADocumentVersion)
            .where(MSADocumentVersion.tracker_id == tracker_id)
            .order_by(MSADocumentVersion.version_number.desc())
            .limit(1)
        ).scalar_one()
        revision.resulting_version_id = latest_version.id
        revision.status = "applied"
        revision.applied_at = datetime.now(timezone.utc)
        db.commit()
        return out

    edited_text = revision.edited_text if revision else payload.edited_text
    # Honour reviewer-curated text: when the reviewer edited the AI's proposal
    # before applying, use their text and persist it onto the revision so the edit
    # history reflects what was actually applied. Restricted to non-DOCX, text-mode
    # revisions so Word documents always keep the formatting-preserving path.
    if (
        revision is not None
        and revision.edit_mode != "docx_operations"
        and not _is_docx_parent(parent)
        and payload.edited_text.strip()
        and payload.edited_text != revision.edited_text
    ):
        edited_text = payload.edited_text
        revision.edited_text = payload.edited_text
    if onlyoffice_enabled() and _is_docx_parent(parent) and not revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use revision_id for DOCX operation-based apply, or OnlyOffice for manual edits.",
        )
    result = _create_legal_redline_from_text(
        db,
        tracker,
        parent,
        edited_text,
        user,
        request,
        audit_action="msa_prompt_edit_applied",
        audit_summary=f"tracker={tracker_id} v={tracker.current_version + 1} instruction={payload.instruction[:200]}",
    )
    if revision:
        revision.status = "applied"
        revision.applied_at = datetime.now(timezone.utc)
        db.commit()
    return result


@router.get("/{tracker_id}/prompt-revisions", response_model=list[MSAPromptRevisionSummary])
def list_prompt_revisions_endpoint(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[MSAPromptRevisionSummary]:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    rows = list_prompt_revisions(db, tracker_id)
    return [MSAPromptRevisionSummary.model_validate(r) for r in rows]


@router.get("/{tracker_id}/prompt-revisions/{revision_id}", response_model=MSAPromptRevisionOut)
def get_prompt_revision(
    tracker_id: int,
    revision_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAPromptRevisionOut:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    revision = db.get(MSAPromptRevision, revision_id)
    if revision is None or revision.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    return _revision_to_out(revision)


@router.post("/{tracker_id}/prompt-revisions/{revision_id}/discard", response_model=MSAPromptRevisionOut)
def discard_prompt_revision(
    tracker_id: int,
    revision_id: int,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAPromptRevisionOut:
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if level == ACCESS_VIEW:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit access required")
    revision = db.get(MSAPromptRevision, revision_id)
    if revision is None or revision.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    if revision.status == "applied":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot discard an applied revision")
    revision.status = "discarded"
    write_audit(
        db,
        user=user,
        action_type="msa_prompt_edit_discarded",
        module="msa_automation",
        input_summary=f"tracker={tracker_id} revision_id={revision_id}",
        human_decision="discarded",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
    )
    db.commit()
    db.refresh(revision)
    return _revision_to_out(revision)


@router.delete("/{tracker_id}/prompt-revisions/{revision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt_revision(
    tracker_id: int,
    revision_id: int,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> None:
    """Permanently remove a proposed or discarded edit from history (applied stays)."""
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if level == ACCESS_VIEW:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit access required")
    revision = db.get(MSAPromptRevision, revision_id)
    if revision is None or revision.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    if revision.status == "applied":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete an applied revision — it remains in the audit trail",
        )
    write_audit(
        db,
        user=user,
        action_type="msa_prompt_edit_deleted",
        module="msa_automation",
        input_summary=f"tracker={tracker_id} revision_id={revision_id} status={revision.status}",
        human_decision="deleted",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
    )
    db.delete(revision)
    db.commit()
    return None


@router.post("/{tracker_id}/suggestions/preview", response_model=MSASuggestionsPreview)
def suggestions_preview(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSASuggestionsPreview:
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    parent = _latest_legal_version(db, tracker_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No document version available")
    base_text = parent.extracted_text or ""
    suggestions = list(tracker.ai_suggestions or [])
    edited_text, applied, blocked = compile_accepted_suggestions(base_text, suggestions)
    accepted = [s for s in suggestions if s.get("decision") in ("accept", "modify")]
    return MSASuggestionsPreview(
        base_version_id=parent.id,
        base_version_number=parent.version_number,
        base_text=base_text,
        edited_text=edited_text,
        diff_blocks=_line_diff(base_text, edited_text),
        applied_count=len(applied),
        blocked_count=len(blocked),
        accepted_count=len(accepted),
        applied=applied,
        blocked=blocked,
    )


@router.post("/{tracker_id}/suggestions/apply", response_model=MSAOut)
def suggestions_apply(
    tracker_id: int,
    payload: MSASuggestionsApply,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    if tracker.status == "executed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Negotiation already executed")
    parent = db.get(MSADocumentVersion, payload.parent_version_id)
    if parent is None or parent.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent version not found")
    suggestions = list(tracker.ai_suggestions or [])
    base_text = parent.extracted_text or ""
    edited_text, applied, blocked = compile_accepted_suggestions(base_text, suggestions)
    if payload.edited_text.strip() and payload.edited_text != edited_text:
        edited_text = payload.edited_text
    if not applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accepted suggestions could be applied. Review blocked items in preview.",
        )
    if blocked and not payload.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{len(blocked)} suggestion(s) blocked — set force=true to apply partial changes",
        )

    tracker.change_history = append_change_entry(
        tracker.change_history,
        source="ai_suggestion",
        status="applied",
        before=base_text[:500],
        after=edited_text[:500],
        rationale=f"Applied {len(applied)} suggestion(s) in {payload.change_mode} mode",
        decided_by_id=user.id,
    )
    flag_modified(tracker, "change_history")

    if _is_docx_parent(parent) and parent.storage_key:
        parent_bytes = get_document_storage().download(parent.storage_key)
        pairs = replacement_pairs(applied)
        new_bytes = apply_replacements_to_docx(parent_bytes, pairs) if pairs else None
        if new_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not apply suggestions while preserving DOCX formatting. Edit in OnlyOffice.",
            )
        try:
            extracted = parse_document(new_bytes, parent.filename or "edit.docx", parent.mime_type)
        except DocumentParseError:
            extracted = edited_text
        return _create_legal_redline_from_bytes(
            db,
            tracker,
            parent,
            new_bytes,
            extracted,
            user,
            request,
            audit_action="msa_suggestions_applied",
            audit_summary=f"tracker={tracker_id} applied={len(applied)} blocked={len(blocked)} docx",
        )

    return _create_legal_redline_from_text(
        db,
        tracker,
        parent,
        edited_text,
        user,
        request,
        audit_action="msa_suggestions_applied",
        audit_summary=f"tracker={tracker_id} applied={len(applied)} blocked={len(blocked)}",
    )


@router.post("/{tracker_id}/human-edit/apply", response_model=MSAOut)
def human_edit_apply(
    tracker_id: int,
    payload: MSAHumanEditApply,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    """Save direct human edits as a new legal redline version."""
    if not payload.edited_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="edited_text is required")
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    if tracker.status == "executed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Negotiation already executed")
    parent = db.get(MSADocumentVersion, payload.parent_version_id)
    if parent is None or parent.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent version not found")
    if onlyoffice_enabled() and _is_docx_parent(parent):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the OnlyOffice editor to save DOCX changes — formatting is preserved on save.",
        )
    return _create_legal_redline_from_text(
        db,
        tracker,
        parent,
        payload.edited_text,
        user,
        request,
        audit_action="msa_human_edit_applied",
        audit_summary=f"tracker={tracker_id} human_edit v={tracker.current_version + 1}",
    )


@router.get("/{tracker_id}/versions/{version_id}/onlyoffice-config", response_model=OnlyOfficeConfigOut)
def onlyoffice_editor_config(
    tracker_id: int,
    version_id: int,
    request: Request,
    mode: str = "edit",
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> OnlyOfficeConfigOut:
    if not onlyoffice_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OnlyOffice is not enabled")
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    version = db.get(MSADocumentVersion, version_id)
    if version is None or version.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    if not version.storage_key or not is_office_editable(version.filename, version.mime_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version is not an editable Office document")

    # No Bearer token is required here. This used to demand one and reject
    # everything else, which broke the editor once the SPA moved to an httpOnly
    # session cookie: the browser sends no Authorization header, so every request
    # 401'd and the global unauthorized handler bounced the user to the dashboard.
    # The caller is already authenticated by require_msa_module +
    # load_tracker_with_access, and the Document Server does not use the caller's
    # token — build_document_url mints its own scoped file-download token.
    can_edit = (
        tracker.status != "executed"
        and mode == "edit"
        and level in (ACCESS_OWNER, ACCESS_EDIT)
    )
    config = build_editor_config(
        version_id=version.id,
        sha256=version.sha256,
        filename=version.filename,
        mime_type=version.mime_type,
        storage_key=version.storage_key,
        user_id=user.id,
        user_name=user.full_name,
        tracker_id=tracker_id,
        parent_version_id=version.id,
        mode="view" if not can_edit else "edit",
        can_edit=can_edit,
    )
    return OnlyOfficeConfigOut(
        document_server_url=settings.onlyoffice_public_url,
        token=sign_config(config),
        config=config,
        enabled=True,
    )


@router.post(
    "/{tracker_id}/versions/{version_id}/onlyoffice-save",
    response_model=OnlyOfficeForcesaveOut,
)
def onlyoffice_forcesave(
    tracker_id: int,
    version_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> OnlyOfficeForcesaveOut:
    """Trigger ONLYOFFICE forcesave so manual edits become a new legal redline version."""
    if not onlyoffice_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OnlyOffice is not enabled")
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    if tracker.status == "executed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Negotiation already executed")
    version = db.get(MSADocumentVersion, version_id)
    if version is None or version.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    if not version.storage_key or not is_office_editable(version.filename, version.mime_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version is not an editable Office document")

    key = document_key(version.id, version.sha256)
    # Command-service forcesave (forcesavetype 0) echoes THIS userdata back to our
    # callback — not the editor config one — so the callback can map the save to
    # the right tracker/version and create the new redline version.
    userdata = json.dumps(
        {
            "tracker_id": tracker_id,
            "parent_version_id": version.id,
            "user_id": user.id,
        }
    )
    # Error 4 = "no changes yet": the editor may not have flushed edits into the
    # Document Server cache. Retry briefly to let autosave catch up.
    error_code = -1
    for attempt in range(4):
        try:
            error_code = trigger_forcesave(key, userdata=userdata)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        if error_code != 4 or attempt == 3:
            break
        time.sleep(1.5)

    if error_code == 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes to save")
    if error_code == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document editor session not found — reload the page and try again",
        )
    if error_code != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ONLYOFFICE forcesave failed (error {error_code})",
        )
    return OnlyOfficeForcesaveOut(accepted=True, error_code=error_code)


@router.post("/{tracker_id}/compare", response_model=NegotiationChangesOut)
def compare_versions_endpoint(
    tracker_id: int,
    request: Request,
    from_version_id: int,
    to_version_id: int,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> NegotiationChangesOut:
    """Run a fresh compare between any two versions. Returns the same shape
    as /changes so the frontend can render it identically."""
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_OWNER)
    from_v = db.get(MSADocumentVersion, from_version_id)
    to_v = db.get(MSADocumentVersion, to_version_id)
    if (
        from_v is None
        or to_v is None
        or from_v.tracker_id != tracker_id
        or to_v.tracker_id != tracker_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    if from_v.id == to_v.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pick two different versions")
    comp = compare_two_versions(db, tracker, from_v, to_v, user)
    # Keep tracker-level summary panels in sync with ad-hoc compare results.
    narrative = comp.llm_narrative or []
    if narrative:
        synthesized = synthesize_suggestions_from_narrative(narrative)
        tracker.ai_suggestions = synthesized
        tracker.risk_score = risk_score_from_suggestions(synthesized)
    db.commit()
    db.refresh(comp)
    narrative = comp.llm_narrative or []
    items = [NegotiationChangeItemOut(**n) for n in narrative] if narrative else []
    return NegotiationChangesOut(
        comparison_id=comp.id,
        summary_report=comp.summary_report,
        executive_summary=comp.summary_report,
        diff_blocks=comp.diff_blocks,
        risk_commentary=comp.risk_commentary,
        llm_narrative=items,
        from_version_number=from_v.version_number,
        to_version_number=to_v.version_number,
    )


@router.get("/{tracker_id}/changes", response_model=NegotiationChangesOut)
def get_changes(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> NegotiationChangesOut:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    comp = get_latest_changes(db, tracker_id)
    if comp is None:
        return NegotiationChangesOut(
            comparison_id=None,
            summary_report=None,
            executive_summary=None,
            diff_blocks=[],
            risk_commentary=[],
            llm_narrative=[],
            from_version_number=None,
            to_version_number=None,
        )
    narrative = comp.llm_narrative or []
    exec_summary = comp.summary_report
    if narrative and isinstance(narrative[0], dict):
        items = [NegotiationChangeItemOut(**n) for n in narrative]
    else:
        items = []
    from_vn = to_vn = None
    if comp.from_version_id:
        fv = db.get(MSADocumentVersion, comp.from_version_id)
        from_vn = fv.version_number if fv else None
    if comp.to_version_id:
        tv = db.get(MSADocumentVersion, comp.to_version_id)
        to_vn = tv.version_number if tv else None
    return NegotiationChangesOut(
        comparison_id=comp.id,
        summary_report=comp.summary_report,
        executive_summary=exec_summary,
        diff_blocks=comp.diff_blocks,
        risk_commentary=comp.risk_commentary,
        llm_narrative=items,
        from_version_number=from_vn,
        to_version_number=to_vn,
    )


@router.get("/{tracker_id}/memory", response_model=list[NegotiationMemoryOut])
def list_negotiation_memory(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[NegotiationMemoryOut]:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    rows = list_memory(db, tracker_id, limit=50)
    return [NegotiationMemoryOut.model_validate(r) for r in rows]


@router.get("/{tracker_id}/review-history")
def get_review_history(
    tracker_id: int,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> dict:
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    return {"change_history": tracker.change_history or []}


@router.get("/{tracker_id}/tasks", response_model=list[NegotiationTaskOut])
def list_tasks(
    tracker_id: int,
    status_filter: str | None = None,
    include_low: bool = False,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> list[NegotiationTaskOut]:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
    q = select(NegotiationChangeTask).where(NegotiationChangeTask.tracker_id == tracker_id)
    if status_filter:
        q = q.where(NegotiationChangeTask.status == status_filter)
    if not include_low:
        q = q.where(NegotiationChangeTask.severity != "low")
    rows = db.execute(q.order_by(NegotiationChangeTask.created_at.desc())).scalars().all()
    return [NegotiationTaskOut.model_validate(t) for t in rows]


@router.patch("/{tracker_id}/tasks/{task_id}", response_model=NegotiationTaskOut)
def update_task(
    tracker_id: int,
    task_id: int,
    payload: NegotiationTaskUpdate,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> NegotiationTaskOut:
    load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_OWNER)
    task = db.get(NegotiationChangeTask, task_id)
    if task is None or task.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if payload.status is not None:
        task.status = payload.status
        if payload.status == "resolved":
            task.resolved_at = datetime.now(timezone.utc)
    if payload.assigned_to_id is not None:
        task.assigned_to_id = payload.assigned_to_id
    write_audit(
        db,
        user=user,
        action_type="msa_change_task_resolved",
        module="msa_automation",
        input_summary=f"task={task_id} status={task.status}",
        human_decision=task.status,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
    )
    db.commit()
    db.refresh(task)
    return NegotiationTaskOut.model_validate(task)


@router.post("/{tracker_id}/tasks/{task_id}/promote", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def promote_negotiation_task(
    tracker_id: int,
    task_id: int,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> TaskOut:
    from app.core.rbac import Role, has_permission

    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not has_permission(Role(user.role), Permission.TASK_MANAGEMENT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Task Manager permission required to promote items",
        )
    task = db.get(NegotiationChangeTask, task_id)
    if task is None or task.tracker_id != tracker_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.promoted_task_id:
        existing = db.get(Task, task.promoted_task_id)
        if existing:
            return TaskOut.model_validate(existing)
    priority_map = {"high": "high", "medium": "medium", "low": "low"}
    priority = priority_map.get((task.severity or "medium").lower(), "medium")
    global_task = Task(
        title=task.title,
        description=task.description,
        source="module",
        source_module="msa_automation",
        source_ref_id=task.id,
        priority=priority,
        priority_score=0.9 if priority == "high" else 0.6,
        status="todo",
        due_date=task.due_date,
        tags=[f"msa:{tracker_id}", tracker.vendor_name],
        ai_confidence=0.85,
        ai_rationale=f"Promoted from MSA negotiation: {tracker.vendor_name}",
        model_version=orch_tasks.model_version(),
        created_by_id=user.id,
        assigned_to_id=task.assigned_to_id or tracker.assigned_to_id or user.id,
    )
    db.add(global_task)
    db.flush()
    task.promoted_task_id = global_task.id
    write_audit(
        db,
        user=user,
        action_type="msa_task_promoted",
        module="msa_automation",
        input_summary=task.title[:300],
        ai_output_summary=f"task_id={global_task.id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker_id,
        extra={"negotiation_task_id": task.id, "global_task_id": global_task.id},
    )
    db.commit()
    db.refresh(global_task)
    return TaskOut.model_validate(global_task)


@router.post("/{tracker_id}/finalize", response_model=MSAOut)
def finalize_tracker(
    tracker_id: int,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    from app.core.rbac import Role, has_permission

    if not has_permission(Role(user.role), Permission.APPROVE_AI_OUTPUT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_OWNER)
    if tracker.canonical_version_id:
        canon = db.get(MSADocumentVersion, tracker.canonical_version_id)
        if canon:
            final_v, _ = create_version(
                db,
                tracker,
                source="executed_final",
                extracted_text=canon.extracted_text,
                user=user,
                filename=canon.filename,
                storage_key=canon.storage_key,
                sha256=canon.sha256,
                parent_version_id=canon.id,
                run_compare=False,
                ip_address=client_ip(request),
                session_id=session_id(request),
            )
            tracker.executed_version_id = final_v.id
    tracker.status = "executed"
    from app.services.notify_hooks import notify_msa_executed

    _recipients: list[User] = []
    if tracker.assigned_to_id:
        _owner = db.get(User, tracker.assigned_to_id)
        if _owner:
            _recipients.append(_owner)
    for _s in db.execute(select(MSAShare).where(MSAShare.tracker_id == tracker_id)).scalars().all():
        _u = db.get(User, _s.user_id)
        if _u:
            _recipients.append(_u)
    notify_msa_executed(db, _recipients, tracker.vendor_name or "a vendor", tracker_id)
    write_audit(
        db,
        user=user,
        action_type="msa_finalized",
        module="msa_automation",
        input_summary=f"tracker={tracker_id}",
        human_decision="executed",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


@router.get("/files/{storage_key:path}")
def download_file(
    storage_key: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    # Prefer query token for ONLYOFFICE fetches. The document server can send
    # its own Authorization header, which should not override our file token.
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
    # Session cookie last: the SPA fetches previews with credentials and no header,
    # so without this the in-app document viewer 401s on every file.
    if not token:
        token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")

    if payload.get("purpose") == "file_download":
        scoped = payload.get("storage_key")
        if scoped != storage_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Download token is not valid for this file",
            )
    return _download_file(storage_key, user)


def _download_file(storage_key: str, user: User) -> Response:
    data = get_document_storage().download(storage_key)
    ext = storage_key.rsplit(".", 1)[-1].lower() if "." in storage_key else ""
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain",
        "md": "text/markdown",
    }.get(ext, "application/octet-stream")
    return Response(content=data, media_type=media_type)


@router.post("/{tracker_id}/suggestions/decide-all", response_model=MSAOut)
def decide_all_suggestions(
    tracker_id: int,
    payload: MSADecideAll,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    if payload.decision not in {"accept", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision")
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    suggestions = [dict(s) for s in (tracker.ai_suggestions or [])]
    updated_count = 0
    for s in suggestions:
        if s.get("decision") == "pending":
            s["decision"] = payload.decision
            record_decision(
                db,
                tracker.id,
                suggestion_id=int(s.get("order_index", 0)),
                decision=payload.decision,
                user_id=user.id,
            )
            updated_count += 1
    if updated_count == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending suggestions")
    tracker.ai_suggestions = suggestions
    flag_modified(tracker, "ai_suggestions")
    write_audit(
        db,
        user=user,
        action_type="msa_decision_all",
        module="msa_automation",
        input_summary=f"decision={payload.decision} count={updated_count}",
        human_decision=payload.decision,
        model_version=None,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


@router.post("/{tracker_id}/decide", response_model=MSAOut)
def decide_suggestion(
    tracker_id: int,
    payload: MSADecision,
    request: Request,
    user: User = Depends(require_msa_module),
    db: Session = Depends(get_db),
) -> MSAOut:
    if payload.decision not in {"accept", "modify", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision")
    tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_EDIT)
    if not can_apply_msa_changes(user, level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")
    # Copy each dict (not just the list) so the ORM's committed snapshot isn't
    # mutated in place — ai_suggestions is a plain JSON column without Mutable
    # tracking, so in-place edits go undetected and the UPDATE is never emitted.
    suggestions = [dict(s) for s in (tracker.ai_suggestions or [])]
    updated = False
    for s in suggestions:
        if s.get("order_index") == payload.suggestion_id:
            s["decision"] = payload.decision
            if payload.reviewer_edit is not None:
                s["reviewer_edit"] = payload.reviewer_edit
            updated = True
            tracker.change_history = append_change_entry(
                tracker.change_history,
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
    tracker.ai_suggestions = suggestions
    flag_modified(tracker, "ai_suggestions")
    flag_modified(tracker, "change_history")
    record_decision(
        db,
        tracker.id,
        suggestion_id=payload.suggestion_id,
        decision=payload.decision,
        user_id=user.id,
    )
    write_audit(
        db,
        user=user,
        action_type="msa_decision",
        module="msa_automation",
        input_summary=f"suggestion={payload.suggestion_id}",
        human_decision=payload.decision,
        model_version=None,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)


@router.post("/{tracker_id}/send", response_model=MSAOut)
def send_email(
    tracker_id: int,
    payload: MSASendEmail,
    request: Request,
    user: User = Depends(require_msa_owner),
    db: Session = Depends(get_db),
) -> MSAOut:
    from app.core.rbac import Role, has_permission

    if not has_permission(Role(user.role), Permission.SEND_EMAIL):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Send email permission required")
    tracker, _ = load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_OWNER)
    if not tracker.redlined_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generate redline before sending",
        )
    attachment_bytes = tracker.redlined_text.encode("utf-8")
    attachment_name = f"{tracker.vendor_name}_v{tracker.current_version}_redlined.txt"
    storage_key, _ = get_document_storage().upload(
        attachment_bytes, attachment_name, "text/plain"
    )
    version_id = tracker.canonical_version_id
    gmail_msg_id = None
    thread_id = tracker.gmail_thread_id
    svc = get_gmail_service()
    if settings.gmail_enabled and svc.is_configured():
        try:
            sent = svc.send_message(
                db,
                user,
                to_addr=tracker.vendor_email,
                subject=payload.subject,
                body=payload.body,
                thread_id=thread_id,
                attachment_bytes=attachment_bytes,
                attachment_name=attachment_name,
            )
            gmail_msg_id = sent.get("id")
            thread_id = sent.get("threadId") or thread_id
            tracker.gmail_thread_id = thread_id
            tracker.gmail_auto_ingest = True
            add_msa_watch(
                db,
                user,
                thread_id=thread_id,
                tracker_id=tracker.id,
                subject=payload.subject,
                vendor_email=tracker.vendor_email,
            )
        except RuntimeError:
            pass
    db.add(
        MSAEmail(
            tracker_id=tracker.id,
            version_id=version_id,
            direction="out",
            from_addr="legal@jfpsl.in",
            to_addr=tracker.vendor_email,
            subject=payload.subject,
            body=payload.body,
            attachment_name=attachment_name,
            attachment_storage_key=storage_key,
            gmail_message_id=gmail_msg_id,
            sent_at=datetime.now(timezone.utc),
            sent_by_id=user.id,
        )
    )
    tracker.status = "sent_to_vendor"
    write_audit(
        db,
        user=user,
        action_type="msa_sent",
        module="msa_automation",
        input_summary=f"to={tracker.vendor_email} version=v{tracker.current_version}",
        human_decision="sent",
        model_version=None,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=tracker.id,
        extra={"subject": payload.subject},
    )
    db.commit()
    db.refresh(tracker)
    return _to_out(tracker, user=user, db=db)
