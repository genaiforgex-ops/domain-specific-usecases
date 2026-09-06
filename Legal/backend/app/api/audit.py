from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rbac import Permission, Role, has_permission
from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    module: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[AuditLogOut]:
    """Caller sees ALL logs if they have AUDIT_LOG_ALL, else only their own
    rows (AUDIT_LOG_OWN). No role can mutate this log via API.
    """
    role = Role(user.role)
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if not has_permission(role, Permission.AUDIT_LOG_ALL):
        stmt = stmt.where(AuditLog.user_id == user.id)
    if module:
        stmt = stmt.where(AuditLog.module == module)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    rows = db.execute(stmt).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]
