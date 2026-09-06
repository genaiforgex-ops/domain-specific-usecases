import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    client_ip,
    get_current_user,
    require_permission,
    require_super_admin,
    session_id,
)
from app.config import settings
from app.core.rbac import ROLE_PERMISSIONS, Permission, Role
from app.core.security import create_invite_token, hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    IamSyncResultOut,
    InviteRequest,
    InviteResult,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import notification_templates as tpl
from app.services.audit_service import write_audit
from app.services.iam_sync_service import sync_all_users_from_iam
from app.services.notification_service import get_notification_service
from app.services.user_service import hard_delete_user


router = APIRouter(prefix="/api/users", tags=["users"])

_IAM_MANAGED_MSG = "Users and roles are managed centrally via IAM. Changes must be made in the Central Platform."


def _block_if_iam_managed(user: User) -> None:
    if user.iam_managed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_IAM_MANAGED_MSG)


def _block_if_central_iam_enabled() -> None:
    if settings.iam_sync_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_IAM_MANAGED_MSG)


def _serialize(user: User) -> UserOut:
    perms: list[str] = []
    try:
        perms = sorted(p.value for p in ROLE_PERMISSIONS.get(Role(user.role), set()))
    except ValueError:
        perms = []
    return UserOut.model_validate({**user.__dict__, "permissions": perms})


def _role_label(role: str) -> str:
    return role.replace("_", " ").title()


def _active_super_admin_count(db: Session, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(
        User.role == Role.SUPER_ADMIN.value, User.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.execute(stmt).scalar_one())


def _send_invite(db: Session, user: User, inviter: User) -> tuple[bool, str]:
    """Mint an invite link and email it. Returns (email_sent, detail). Never raises."""
    token = create_invite_token(user.id, user.email)
    accept_url = f"{settings.frontend_base_url.rstrip('/')}/accept-invite?token={token}"
    subject, html, text = tpl.invite(
        recipient_name=user.full_name.split(" ")[0] if user.full_name else "",
        inviter_name=inviter.full_name or "A colleague",
        role_label=_role_label(user.role),
        accept_url=accept_url,
    )
    try:
        get_notification_service().send_transactional(user.email, subject, html, text)
        return True, f"Invite sent to {user.email}."
    except Exception as exc:  # noqa: BLE001 — report, don't fail the request
        return False, f"Invite created but the email could not be sent ({exc}). Use Resend."


@router.get("", response_model=list[UserOut])
async def list_users(
    _: User = Depends(require_permission(Permission.USER_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    if settings.iam_sync_enabled:
        await sync_all_users_from_iam(db)
        db.commit()
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [_serialize(u) for u in users]


@router.post("/sync", response_model=IamSyncResultOut)
async def sync_users_from_iam(
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> IamSyncResultOut:
    if not settings.iam_sync_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM sync is not configured (IAM_CLIENT_SECRET missing).",
        )
    result = await sync_all_users_from_iam(db)
    write_audit(
        db,
        user=actor,
        action_type="iam_user_sync",
        module="users",
        input_summary=(
            f"created={result.created} updated={result.updated} "
            f"deactivated={result.deactivated} unchanged={result.unchanged}"
        ),
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    return IamSyncResultOut(
        created=result.created,
        updated=result.updated,
        deactivated=result.deactivated,
        unchanged=result.unchanged,
    )


@router.post("/invite", response_model=InviteResult, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: InviteRequest,
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> InviteResult:
    _block_if_central_iam_enabled()
    try:
        Role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role") from exc

    email = payload.email.lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing and existing.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")

    if existing:
        # Re-invite a pending (inactive) invitee: refresh their details.
        existing.full_name = payload.full_name
        existing.role = payload.role
        user = existing
    else:
        user = User(
            email=email,
            # Unusable placeholder — login is blocked until the invite is accepted.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name=payload.full_name,
            role=payload.role,
            is_active=False,
        )
        db.add(user)
    db.flush()

    email_sent, detail = _send_invite(db, user, actor)
    write_audit(
        db,
        user=actor,
        action_type="user_invited",
        module="users",
        input_summary=f"email={email} role={payload.role} email_sent={email_sent}",
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    db.refresh(user)
    return InviteResult(user=_serialize(user), email_sent=email_sent, detail=detail)


@router.post("/{user_id}/resend-invite", response_model=InviteResult)
def resend_invite(
    user_id: int,
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> InviteResult:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _block_if_iam_managed(user)
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user has already activated their account",
        )
    email_sent, detail = _send_invite(db, user, actor)
    write_audit(
        db,
        user=actor,
        action_type="invite_resent",
        module="users",
        input_summary=f"email={user.email} email_sent={email_sent}",
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    return InviteResult(user=_serialize(user), email_sent=email_sent, detail=detail)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    _block_if_central_iam_enabled()
    try:
        Role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role") from exc
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        user=actor,
        action_type="user_created",
        module="users",
        input_summary=f"email={payload.email} role={payload.role}",
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _block_if_iam_managed(user)

    if payload.full_name is not None:
        user.full_name = payload.full_name

    if payload.role is not None:
        try:
            Role(payload.role)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role") from exc
        # Guard: don't demote the last active Super Admin out of the role.
        if (
            user.role == Role.SUPER_ADMIN.value
            and payload.role != Role.SUPER_ADMIN.value
            and user.is_active
            and _active_super_admin_count(db, exclude_id=user.id) == 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change the role of the last active Super Admin",
            )
        user.role = payload.role

    if payload.is_active is not None:
        # Guard: don't deactivate the last active Super Admin.
        if (
            not payload.is_active
            and user.role == Role.SUPER_ADMIN.value
            and user.is_active
            and _active_super_admin_count(db, exclude_id=user.id) == 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active Super Admin",
            )
        user.is_active = payload.is_active

    write_audit(
        db,
        user=actor,
        action_type="user_updated",
        module="users",
        input_summary=payload.model_dump_json(exclude_none=True),
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    from fastapi import Response

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _block_if_iam_managed(user)
    if user.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account"
        )
    if (
        user.role == Role.SUPER_ADMIN.value
        and user.is_active
        and _active_super_admin_count(db, exclude_id=user.id) == 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last active Super Admin",
        )
    # Audit first (references the actor, who is preserved), then delete.
    write_audit(
        db,
        user=actor,
        action_type="user_deleted",
        module="users",
        input_summary=f"email={user.email} role={user.role}",
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    hard_delete_user(db, user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/permissions", response_model=list[str])
def my_permissions(user: User = Depends(get_current_user)) -> list[str]:
    try:
        return sorted(p.value for p in ROLE_PERMISSIONS.get(Role(user.role), set()))
    except ValueError:
        return []
