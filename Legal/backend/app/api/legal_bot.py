"""UC-03 LegalBot (Basic Legal Queries)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_permission, session_id
from app.core.rbac import Permission, Role
from app.database import get_db
from app.models.msa_version import MSADocumentVersion
from app.models.playbook import KnowledgeBaseEntry
from app.models.query import LegalBotQuery
from app.models.user import User
from app.schemas.query import QueryCreate, QueryOut, QueryOverride
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.msa_access import ACCESS_VIEW, load_tracker_with_access
from app.services.gmail_service import get_gmail_service
from app.services.negotiation_memory_service import memory_snippets, record_bot_qa


router = APIRouter(prefix="/api/legal-bot", tags=["legal-bot"])


def _latest_msa_version_text(db: Session, tracker_id: int, version_id: int | None) -> tuple[str, int | None]:
    if version_id is not None:
        version = db.get(MSADocumentVersion, version_id)
        if version is None or version.tracker_id != tracker_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MSA version not found")
        return (version.extracted_text or "")[:50000], version.id
    row = db.execute(
        select(MSADocumentVersion)
        .where(
            MSADocumentVersion.tracker_id == tracker_id,
            MSADocumentVersion.source.in_(["legal_redline", "legal_base"]),
        )
        .order_by(MSADocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No document version available")
    return (row.extracted_text or "")[:50000], row.id


def _to_out(q: LegalBotQuery) -> QueryOut:
    return QueryOut.model_validate(q.__dict__)


@router.post("/ask", response_model=QueryOut, status_code=status.HTTP_201_CREATED)
def ask(
    payload: QueryCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> QueryOut:
    if not payload.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question is required")
    kb = db.execute(select(KnowledgeBaseEntry)).scalars().all()

    context_type = payload.context_type or "none"
    context_tracker_id = payload.context_tracker_id
    context_version_id = payload.context_version_id
    document_text = ""
    mem: list[str] = []

    if context_type == "msa_version":
        if context_tracker_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="context_tracker_id is required for msa_version context",
            )
        load_tracker_with_access(context_tracker_id, user, db, min_level=ACCESS_VIEW)
        document_text, resolved_version_id = _latest_msa_version_text(
            db, context_tracker_id, context_version_id
        )
        context_version_id = resolved_version_id
        mem = memory_snippets(db, context_tracker_id)
        result = orch_tasks.answer_legal_bot(
            payload.question,
            kb,
            module="legal_bot",
            operation="answer_query",
            user_id=user.id,
            db=db,
            document_text=document_text,
            memory_snippets=mem,
        )
        record_bot_qa(
            db,
            context_tracker_id,
            payload.question,
            result.answer or "",
            user.id,
            version_id=context_version_id,
        )
    elif context_type == "gmail_thread":
        thread_id = payload.context_gmail_thread_id
        if not thread_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="context_gmail_thread_id is required for gmail_thread context",
            )
        svc = get_gmail_service()
        try:
            document_text = svc.thread_as_text(db, user, thread_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        result = orch_tasks.answer_legal_bot(
            payload.question,
            kb,
            module="legal_bot",
            operation="answer_query",
            user_id=user.id,
            db=db,
            document_text=document_text,
        )
    else:
        result = orch_tasks.answer_legal_bot(
            payload.question,
            kb,
            module="legal_bot",
            operation="answer_query",
            user_id=user.id,
            db=db,
        )

    q = LegalBotQuery(
        user_id=user.id,
        question=payload.question,
        ai_answer=result.answer,
        citations=result.citations,
        confidence=result.confidence,
        tier=result.tier,
        status="answered" if result.tier == 1 else "escalated",
        model_version=result.model_version,
        context_type=context_type if context_type != "none" else None,
        context_tracker_id=context_tracker_id,
        context_version_id=context_version_id,
        context_gmail_thread_id=payload.context_gmail_thread_id,
    )
    db.add(q)
    db.flush()
    if result.tier != 1:
        from app.services.notify_hooks import notify_approval_escalation

        notify_approval_escalation(db, payload.question, q.id)
    write_audit(
        db,
        user=user,
        action_type="legal_bot_query",
        module="legal_bot",
        input_summary=payload.question[:500],
        ai_output_summary=result.answer[:500] if result.answer else "",
        confidence_score=result.confidence,
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=q.id,
        extra={"tier": result.tier, "context_type": context_type},
    )
    db.commit()
    db.refresh(q)
    return _to_out(q)


@router.get("/my-queries", response_model=list[QueryOut])
def my_queries(
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[QueryOut]:
    rows = (
        db.execute(
            select(LegalBotQuery).where(LegalBotQuery.user_id == user.id).order_by(LegalBotQuery.id.desc())
        )
        .scalars()
        .all()
    )
    return [_to_out(q) for q in rows]


@router.get("/escalated", response_model=list[QueryOut])
def escalated_queue(
    _: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> list[QueryOut]:
    rows = (
        db.execute(
            select(LegalBotQuery)
            .where(LegalBotQuery.status == "escalated")
            .order_by(LegalBotQuery.id.desc())
        )
        .scalars()
        .all()
    )
    return [_to_out(q) for q in rows]


@router.post("/{query_id}/override", response_model=QueryOut)
def override_response(
    query_id: int,
    payload: QueryOverride,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> QueryOut:
    q = db.get(LegalBotQuery, query_id)
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    q.legal_override = payload.legal_override
    q.overridden_by_id = user.id
    q.status = "resolved"
    q.resolved_at = datetime.now(timezone.utc)
    if q.user_id and q.user_id != user.id:
        from app.services.notify_hooks import notify_approval_resolved

        asker = db.get(User, q.user_id)
        if asker is not None:
            notify_approval_resolved(db, asker, q.question, q.id)
    write_audit(
        db,
        user=user,
        action_type="legal_bot_override",
        module="legal_bot",
        input_summary=q.question[:500],
        ai_output_summary=(q.ai_answer or "")[:500],
        human_decision="override",
        confidence_score=q.confidence,
        model_version=q.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=q.id,
        extra={"override_excerpt": payload.legal_override[:200]},
    )
    db.commit()
    db.refresh(q)
    return _to_out(q)


@router.get("/{query_id}", response_model=QueryOut)
def get_query(
    query_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueryOut:
    q = db.get(LegalBotQuery, query_id)
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    # Business Users can only see their own queries.
    if user.role == Role.BUSINESS_USER.value and q.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access this query")
    return _to_out(q)
