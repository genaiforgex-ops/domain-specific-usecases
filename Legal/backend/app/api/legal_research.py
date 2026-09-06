"""UC-04 Legal Research."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.playbook import RegulatorySource
from app.models.research import ResearchNote
from app.models.user import User
from app.schemas.research import (
    ResearchCreate,
    ResearchOut,
    ResearchSummary,
    ResearchUpdate,
)
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit


router = APIRouter(prefix="/api/legal-research", tags=["legal-research"])


@router.get("", response_model=list[ResearchSummary])
def list_notes(
    _: User = Depends(require_permission(Permission.LEGAL_RESEARCH)),
    db: Session = Depends(get_db),
) -> list[ResearchSummary]:
    rows = db.execute(select(ResearchNote).order_by(ResearchNote.created_at.desc())).scalars().all()
    return [ResearchSummary.model_validate(r) for r in rows]


@router.post("", response_model=ResearchOut, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: ResearchCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_RESEARCH)),
    db: Session = Depends(get_db),
) -> ResearchOut:
    if not payload.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query is required")
    corpus = db.execute(select(RegulatorySource)).scalars().all()
    result = orch_tasks.generate_research_note(
        payload.query,
        corpus,
        module="legal_research",
        operation="generate_research_note",
        user_id=user.id,
        db=db,
    )
    note = ResearchNote(
        query=payload.query,
        summary=result.summary,
        applicable_regulations=result.applicable_regulations,
        key_provisions=result.key_provisions,
        implications=result.implications,
        recommended_next_steps=result.recommended_next_steps,
        citations=result.citations,
        confidence=result.confidence,
        status="draft",
        model_version=result.model_version,
        created_by_id=user.id,
    )
    db.add(note)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="research_drafted",
        module="legal_research",
        input_summary=payload.query[:500],
        ai_output_summary=result.summary[:500],
        confidence_score=result.confidence,
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=note.id,
    )
    db.commit()
    db.refresh(note)
    return ResearchOut.model_validate(note)


@router.get("/{note_id}", response_model=ResearchOut)
def get_note(
    note_id: int,
    _: User = Depends(require_permission(Permission.LEGAL_RESEARCH)),
    db: Session = Depends(get_db),
) -> ResearchOut:
    note = db.get(ResearchNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return ResearchOut.model_validate(note)


@router.patch("/{note_id}", response_model=ResearchOut)
def update_note(
    note_id: int,
    payload: ResearchUpdate,
    request: Request,
    user: User = Depends(require_permission(Permission.APPROVE_AI_OUTPUT)),
    db: Session = Depends(get_db),
) -> ResearchOut:
    note = db.get(ResearchNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if payload.reviewer_notes is not None:
        note.reviewer_notes = payload.reviewer_notes
    if payload.status is not None:
        if payload.status not in {"draft", "finalized"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        note.status = payload.status
        if payload.status == "finalized":
            note.finalized_by_id = user.id
            note.finalized_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user=user,
        action_type="research_updated",
        module="legal_research",
        input_summary=payload.model_dump_json(exclude_none=True),
        human_decision=payload.status or "annotated",
        model_version=note.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=note.id,
    )
    db.commit()
    db.refresh(note)
    return ResearchOut.model_validate(note)
