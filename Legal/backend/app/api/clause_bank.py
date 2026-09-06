from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.clause_bank import ClauseBankEntry
from app.models.user import User
from app.schemas.playbook import (
    ClauseBankEntryCreate,
    ClauseBankEntryOut,
    ClauseBankEntryUpdate,
)
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/clause-bank", tags=["clause-bank"])


@router.get("", response_model=list[ClauseBankEntryOut])
def list_entries(
    contract_type: str | None = None,
    _: User = Depends(
        require_permission(Permission.PLAYBOOK_MANAGEMENT, Permission.CONTRACT_REVIEW)
    ),
    db: Session = Depends(get_db),
) -> list[ClauseBankEntryOut]:
    q = select(ClauseBankEntry).order_by(ClauseBankEntry.clause_type, ClauseBankEntry.tier)
    if contract_type:
        q = q.where(ClauseBankEntry.contract_type.in_([contract_type, "ANY"]))
    rows = db.execute(q).scalars().all()
    return [ClauseBankEntryOut.model_validate(r) for r in rows]


@router.get("/by-contract-type/{contract_type}", response_model=list[ClauseBankEntryOut])
def list_by_contract_type(
    contract_type: str,
    _: User = Depends(require_permission(Permission.CONTRACT_REVIEW, Permission.MSA_AUTOMATION)),
    db: Session = Depends(get_db),
) -> list[ClauseBankEntryOut]:
    rows = (
        db.execute(
            select(ClauseBankEntry).where(
                ClauseBankEntry.contract_type.in_([contract_type, "ANY"]),
                ClauseBankEntry.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    return [ClauseBankEntryOut.model_validate(r) for r in rows]


@router.post("", response_model=ClauseBankEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: ClauseBankEntryCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> ClauseBankEntryOut:
    row = ClauseBankEntry(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="clause_bank_created",
        module="clause_bank",
        input_summary=f"type={payload.clause_type}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return ClauseBankEntryOut.model_validate(row)


@router.patch("/{entry_id}", response_model=ClauseBankEntryOut)
def update_entry(
    entry_id: int,
    payload: ClauseBankEntryUpdate,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> ClauseBankEntryOut:
    row = db.get(ClauseBankEntry, entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    write_audit(
        db,
        user=user,
        action_type="clause_bank_updated",
        module="clause_bank",
        input_summary=f"id={entry_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=entry_id,
    )
    db.commit()
    db.refresh(row)
    return ClauseBankEntryOut.model_validate(row)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(ClauseBankEntry, entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(row)
    write_audit(
        db,
        user=user,
        action_type="clause_bank_deleted",
        module="clause_bank",
        input_summary=f"id={entry_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=entry_id,
    )
    db.commit()
