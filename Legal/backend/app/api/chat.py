"""Chatbot orchestrator API — streaming (SSE) legal assistant.

Endpoints:
  POST /api/chat/sse                  Primary streaming chat (text/event-stream)
  POST /api/chat                      Non-streaming fallback
  GET  /api/chat/sessions             List the caller's sessions (sidebar)
  GET  /api/chat/sessions/{id}        Replay a session's turns
  POST /api/chat/attachments          Upload a document to attach to a turn

Auth/RBAC reuse the existing `require_permission(LEGAL_BOT_USE)` dependency, so
the chatbot inherits the platform's access model. The heavy lifting (memory,
guardrails, streaming) lives in `app/orchestrator/`; this module is HTTP only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import client_ip, get_current_user, require_permission, session_id
from app.core.rbac import Permission
from app.models.user import User
from app.orchestrator import config as orch_config
from app.orchestrator.access import (
    can_access,
    delete_session_data,
    export_session_docx,
    export_turn_docx,
    list_session_shares,
    list_shared_with_me,
    revoke_share,
    session_owner,
    share_session,
)
from app.orchestrator.attachments import store as attachment_store
from app.orchestrator.dependencies import get_session_service
from app.orchestrator.memory import list_sessions, replay_turns
from app.models.chat import ChatTurn
from app.orchestrator.models import (
    AttachmentOut,
    ChatRequest,
    ChatShareEntry,
    FeedbackRequest,
    SessionSummary,
    ShareRequest,
    ShareResult,
    ShareUser,
    TemplateAttachRequest,
    TurnOut,
)
from sqlalchemy import select
from app.orchestrator.pipeline import run_chat_once, run_chat_stream
from app.database import get_db
from app.services.document_parser import DocumentParseError, parse_document
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/chat", tags=["chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so chunks flush live
}


@router.post("/sse")
async def chat_sse(
    body: ChatRequest,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
) -> StreamingResponse:
    ip = client_ip(request)
    http_sid = session_id(request)

    async def _disconnect_check() -> bool:
        return await request.is_disconnected()

    stream = run_chat_stream(
        user_id=user.id,
        role=user.role,
        ip=ip,
        http_session_id=http_sid,
        text=body.text,
        session_id=body.session_id,
        context_refs=body.context,
        generate_headline=body.generate_headline,
        mode=body.mode,
        disconnect_check=_disconnect_check,
    )
    return StreamingResponse(stream, media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/")
async def chat_once(
    body: ChatRequest,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
) -> dict:
    return await run_chat_once(
        user_id=user.id,
        role=user.role,
        ip=client_ip(request),
        http_session_id=session_id(request),
        text=body.text,
        session_id=body.session_id,
        context_refs=body.context,
        mode=body.mode,
    )


@router.get("/sessions", response_model=list[SessionSummary])
def get_sessions(
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    return list_sessions(db, user.id)


@router.get("/users", response_model=list[ShareUser])
def list_shareable_users(
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[ShareUser]:
    """Active users the caller can share a chat with (everyone except self).

    Available to any chat user (not gated behind user-management) so sharing
    works without elevated permissions; returns only display fields.
    """
    rows = (
        db.execute(
            select(User)
            .where(User.is_active.is_(True), User.id != user.id)
            .order_by(User.full_name.asc())
        )
        .scalars()
        .all()
    )
    return [
        ShareUser(id=u.id, email=u.email, full_name=u.full_name, role=u.role) for u in rows
    ]


@router.get("/shared", response_model=list[SessionSummary])
def get_shared_with_me(
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    return list_shared_with_me(db, user.id)


@router.get("/sessions/{chat_session_id}", response_model=list[TurnOut])
def get_session_history(
    chat_session_id: str,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[TurnOut]:
    if not can_access(db, chat_session_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return replay_turns(db, chat_session_id)


@router.post("/sessions/{chat_session_id}/share", response_model=ShareResult)
def share_chat_session(
    chat_session_id: str,
    body: ShareRequest,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> ShareResult:
    if session_owner(db, chat_session_id) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can share this chat")
    result = share_session(db, chat_session_id, user.id, body.emails)
    db.commit()
    return result


@router.get("/sessions/{chat_session_id}/shares", response_model=list[ChatShareEntry])
def get_session_shares(
    chat_session_id: str,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> list[ChatShareEntry]:
    if session_owner(db, chat_session_id) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can list shares")
    return [ChatShareEntry(**row) for row in list_session_shares(db, chat_session_id, user.id)]


@router.delete(
    "/sessions/{chat_session_id}/shares/{shared_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_chat_share(
    chat_session_id: str,
    shared_user_id: int,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> Response:
    if session_owner(db, chat_session_id) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can revoke shares")
    if not revoke_share(db, chat_session_id, user.id, shared_user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/templates")
def list_chat_templates(
    _: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
) -> list[dict]:
    """JFPSL template library for LawGenie Draft (LEGAL_BOT_USE, not MSA-only)."""
    from app.services.gcs_template_library import TemplateLibraryError, list_library

    try:
        items = list_library(doc_kind="template")
    except TemplateLibraryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [
        {
            "name": it.name,
            "filename": it.filename,
            "doc_kind": it.doc_kind,
            "contract_type": it.contract_type,
            "description": it.description,
            "storage_key": it.storage_key,
            "content_type": it.content_type,
            "size_bytes": it.size_bytes,
            "updated_at": it.updated_at.isoformat() if it.updated_at else None,
            "source": it.source,
        }
        for it in items
    ]


@router.post("/templates", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def attach_chat_template(
    body: TemplateAttachRequest,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
) -> AttachmentOut:
    """Preview a library template and attach its text to the chat."""
    from app.services.gcs_template_library import TemplateLibraryError, preview_library_text

    try:
        preview = preview_library_text(body.storage_key)
    except TemplateLibraryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    text = (preview.get("text") or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Template preview is empty")
    filename = (
        preview.get("filename")
        or preview.get("name")
        or body.storage_key.rsplit("/", 1)[-1]
        or "template.txt"
    )
    att = attachment_store.put(user.id, str(filename), text)
    return AttachmentOut(
        attachment_id=att.attachment_id,
        filename=att.filename,
        char_count=len(att.text),
    )


@router.post("/turns/{turn_id}/msa")
def send_turn_to_msa(
    turn_id: int,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> dict:
    """Handoff a Draft turn into an MSA tracker (draft status, skip AI review)."""
    from app.models.msa import MSATracker
    from app.core.rbac import Role, has_permission

    if not has_permission(Role(user.role), Permission.MSA_AUTOMATION):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "MSA Automation permission is required to send a draft to MSA",
        )
    turn = db.get(ChatTurn, turn_id)
    if turn is None or not can_access(db, turn.session_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")
    draft_text = (turn.bot_response or "").strip()
    if not draft_text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turn has no draft text")

    tracker = MSATracker(
        vendor_name="(from LawGenie draft)",
        vendor_email=user.email,
        contract_type="MSA",
        deal_reference=f"lawgenie-turn-{turn.id}",
        status="draft",
        risk_score=None,
        current_version=0,
        original_text=draft_text,
        ai_suggestions=[],
        assigned_to_id=user.id,
    )
    db.add(tracker)
    db.commit()
    db.refresh(tracker)
    return {"tracker_id": tracker.id, "detail": "Draft created in MSA Automation"}


@router.get("/sessions/{chat_session_id}/export")
def export_chat_session(
    chat_session_id: str,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> Response:
    if not can_access(db, chat_session_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    data, filename = export_session_docx(db, chat_session_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/sessions/{chat_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    chat_session_id: str,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> Response:
    if session_owner(db, chat_session_id) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete this chat")
    delete_session_data(db, chat_session_id)
    db.commit()
    # Best-effort removal of the ADK-owned conversation events.
    try:
        await get_session_service().delete_session(
            app_name=orch_config.APP_NAME, user_id=str(user.id), session_id=chat_session_id
        )
    except Exception:  # noqa: BLE001 — app rows already gone; ADK cleanup is best-effort
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_FEEDBACK_VALUES = {"up": 1, "down": -1}


@router.post("/turns/{turn_id}/feedback")
def set_turn_feedback(
    turn_id: int,
    body: FeedbackRequest,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> dict:
    """Save thumbs up/down and/or a free-text comment on one of the caller's turns.

    - Thumbs: send ``value`` only (``up`` / ``down`` / null to clear). Existing
      comments are preserved when rating; clearing the rating also clears the comment.
    - Detailed feedback (help button): send ``comment`` (and optionally ``value``).
    """
    turn = db.get(ChatTurn, turn_id)
    if turn is None or turn.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")

    fields = body.model_fields_set
    if "value" in fields:
        if body.value:
            turn.feedback = _FEEDBACK_VALUES.get(body.value)
        else:
            turn.feedback = None
            turn.feedback_comment = None
    if "comment" in fields:
        turn.feedback_comment = (body.comment or "").strip() or None

    db.commit()
    label = {1: "up", -1: "down"}.get(turn.feedback) if turn.feedback else None
    return {"turn_id": turn_id, "feedback": label, "comment": turn.feedback_comment}


@router.get("/turns/{turn_id}/export")
def export_turn(
    turn_id: int,
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
    db: Session = Depends(get_db),
) -> Response:
    """Download a single assistant answer (with its question + references) as .docx."""
    turn = db.get(ChatTurn, turn_id)
    if turn is None or not can_access(db, turn.session_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")
    data, filename = export_turn_docx(turn)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: UploadFile = File(...),
    user: User = Depends(require_permission(Permission.LEGAL_BOT_USE)),
) -> AttachmentOut:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    try:
        text = parse_document(data, file.filename or "upload", file.content_type)
    except DocumentParseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    att = attachment_store.put(user.id, file.filename or "upload", text)
    return AttachmentOut(
        attachment_id=att.attachment_id,
        filename=att.filename,
        char_count=len(att.text),
    )
