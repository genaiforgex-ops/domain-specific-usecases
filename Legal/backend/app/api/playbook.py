from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.playbook import KnowledgeBaseEntry, PlaybookClause, RegulatorySource
from app.models.user import User
from app.schemas.playbook import (
    KnowledgeBaseOut,
    PlaybookClauseCreate,
    PlaybookClauseOut,
    PlaybookClauseUpdate,
    PlaybookSummaryOut,
    RegulatorySourceOut,
)
from app.services.audit_service import write_audit
from app.services.review_workspace_service import playbook_summary


router = APIRouter(prefix="/api/playbook", tags=["playbook"])


@router.get("/summary/{contract_type}", response_model=PlaybookSummaryOut)
def get_playbook_summary(
    contract_type: str,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW, Permission.MSA_AUTOMATION)),
    db: Session = Depends(get_db),
) -> PlaybookSummaryOut:
    rows = (
        db.execute(
            select(PlaybookClause).where(
                PlaybookClause.contract_type.in_([contract_type, "ANY"])
            )
        )
        .scalars()
        .all()
    )
    return PlaybookSummaryOut(**playbook_summary(contract_type, rows))


@router.get("/clauses", response_model=list[PlaybookClauseOut])
def list_clauses(
    _: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT, Permission.CONTRACT_REVIEW)),
    db: Session = Depends(get_db),
) -> list[PlaybookClauseOut]:
    rows = db.execute(select(PlaybookClause).order_by(PlaybookClause.clause_type)).scalars().all()
    return [PlaybookClauseOut.model_validate(r) for r in rows]


@router.post("/clauses", response_model=PlaybookClauseOut, status_code=status.HTTP_201_CREATED)
def create_clause(
    payload: PlaybookClauseCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> PlaybookClauseOut:
    row = PlaybookClause(
        clause_type=payload.clause_type,
        contract_type=payload.contract_type,
        standard_position=payload.standard_position,
        risk_keywords=payload.risk_keywords,
        fallback_text=payload.fallback_text,
        regulatory_tags=payload.regulatory_tags,
        is_required=payload.is_required,
        insert_anchor_hint=payload.insert_anchor_hint,
        notes=payload.notes,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="playbook_clause_created",
        module="playbook",
        input_summary=f"type={payload.clause_type}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return PlaybookClauseOut.model_validate(row)


@router.patch("/clauses/{clause_id}", response_model=PlaybookClauseOut)
def update_clause(
    clause_id: int,
    payload: PlaybookClauseUpdate,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> PlaybookClauseOut:
    row = db.get(PlaybookClause, clause_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    write_audit(
        db,
        user=user,
        action_type="playbook_clause_updated",
        module="playbook",
        input_summary=f"id={clause_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=clause_id,
    )
    db.commit()
    db.refresh(row)
    return PlaybookClauseOut.model_validate(row)


@router.delete("/clauses/{clause_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clause(
    clause_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PlaybookClause, clause_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    clause_type = row.clause_type
    db.delete(row)
    write_audit(
        db,
        user=user,
        action_type="playbook_clause_deleted",
        module="playbook",
        input_summary=f"id={clause_id} type={clause_type}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=clause_id,
    )
    db.commit()


@router.get("/regulatory-sources", response_model=list[RegulatorySourceOut])
def list_sources(
    _: User = Depends(require_permission(Permission.LEGAL_RESEARCH, Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[RegulatorySourceOut]:
    rows = db.execute(select(RegulatorySource).order_by(RegulatorySource.regulator)).scalars().all()
    return [RegulatorySourceOut.model_validate(r) for r in rows]


@router.get("/knowledge-base", response_model=list[KnowledgeBaseOut])
def list_kb(
    _: User = Depends(require_permission(Permission.LEGAL_BOT_USE, Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[KnowledgeBaseOut]:
    rows = db.execute(select(KnowledgeBaseEntry).order_by(KnowledgeBaseEntry.topic)).scalars().all()
    return [KnowledgeBaseOut.model_validate(r) for r in rows]
