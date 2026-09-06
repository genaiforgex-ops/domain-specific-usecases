"""Banner routes — the Designer's flow: pick the banner template for the brief,
generate hero images with Nano Banana for that template, review and approve them,
export the on-brand banners into a fresh Figma file, then send the exported design
to the Marketing Lead for creative review.

All routes are Designer-only and require the brief to be in the design stage (the
Copywriter has handed off the copies)."""

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.brief import Brief, BriefStage
from app.models.user import User
from app.schemas.banner import (
    BannerCommentResult,
    BannerGenerateRequest,
    BannerImageMessageOut,
    BannerImageOut,
    BannerTemplateSelectRequest,
    FigmaExportRequest,
    FigmaExportResult,
)
from app.schemas.brief import BriefOut
from app.services import banner_image_service, figma_export_service
from app.services.figma.mcp_client import FigmaAuthError, FigmaMCPError

router = APIRouter(prefix="/api/briefs/{brief_id}", tags=["banners"])
logger = logging.getLogger("uvicorn.error")

DESIGNER_ROLE = "DS"
# Every internal role (and the creator) may view a brief's banners — approvers
# need to see the design to sign off on it.
_INTERNAL_ROLES = {"CW", "ML", "PL", "DS", "AD"}


def _viewable_brief(db: Session, brief_id: uuid.UUID, user: User) -> Brief:
    """Resolve a brief whose banners the caller may view (read-only): its creator
    or any internal role — so the Marketing Lead and Product Lead can review the
    design at their approval checkpoints."""
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.creator_id != user.id and user.role not in _INTERNAL_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    return brief


def _designer_brief(db: Session, brief_id: uuid.UUID, user: User) -> Brief:
    """Resolve a brief the Designer may produce banners for right now."""
    if user.role != DESIGNER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Designers only")
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.stage != BriefStage.design.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief has not been handed to the Designer yet",
        )
    if brief.designer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another Designer",
        )
    return brief


@router.put("/banner-template", response_model=BriefOut)
def select_banner_template(
    brief_id: uuid.UUID,
    payload: BannerTemplateSelectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Record the template the Designer picked for this brief — the step before the
    hero images are generated. It art-directs the photos and renders the export, so
    it's stored on the brief and reused by every later action."""
    brief = _designer_brief(db, brief_id, user)
    try:
        brief = banner_image_service.select_template(db, brief, payload.template_id, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BriefOut.model_validate(brief)


@router.get("/banner-images", response_model=list[BannerImageOut])
def list_banner_images(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BannerImageOut]:
    _viewable_brief(db, brief_id, user)
    return [BannerImageOut.model_validate(i) for i in banner_image_service.list_images(db, brief_id)]


@router.get("/banner-images/{image_id}/content")
def banner_image_content(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the raw PNG bytes of one hero image (the review thumbnail)."""
    _viewable_brief(db, brief_id, user)
    img = banner_image_service.get_image(db, brief_id, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(content=img.data, media_type=img.mime_type)


@router.post("/banner-images", response_model=list[BannerImageOut])
def generate_banner_images(
    brief_id: uuid.UUID,
    payload: BannerGenerateRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BannerImageOut]:
    """Generate a Nano Banana hero image for every creative on the brief, composed
    for the chosen banner template (defaults to the gallery's default template)."""
    brief = _designer_brief(db, brief_id, user)
    if not brief.creatives:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This brief has no creatives to illustrate",
        )
    try:
        template_id = banner_image_service.require_template_id(
            db, brief, payload.template_id if payload else None
        )
        images = banner_image_service.generate_images(db, brief, user, template_id=template_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [BannerImageOut.model_validate(i) for i in images]


@router.post("/banner-images/{image_id}/regenerate", response_model=BannerImageOut)
def regenerate_banner_image(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: BannerGenerateRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerImageOut:
    """Regenerate one creative's hero image (resets it to pending review), composed
    for the chosen banner template (defaults to the gallery's default template)."""
    brief = _designer_brief(db, brief_id, user)
    img = banner_image_service.get_image(db, brief_id, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    try:
        template_id = banner_image_service.require_template_id(
            db, brief, payload.template_id if payload else None
        )
        updated = banner_image_service.regenerate_image(
            db, brief, img.creative_id, user, template_id=template_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return BannerImageOut.model_validate(updated)


@router.post("/banner-images/{image_id}/upload", response_model=BannerImageOut)
async def upload_banner_image(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerImageOut:
    """Replace a hero image with a file the Designer uploads — for when the AI
    output isn't right and they'd rather supply their own photo."""
    brief = _designer_brief(db, brief_id, user)
    img = banner_image_service.get_image(db, brief_id, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    data = await file.read()
    try:
        updated = banner_image_service.upload_image(
            db, brief, image_id, data, file.content_type or "", user
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BannerImageOut.model_validate(updated)


@router.post("/banner-images/{image_id}/manual-edit", response_model=BannerCommentResult)
async def manual_edit_banner_image(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    file: UploadFile = File(...),
    summary: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerCommentResult:
    """Store a Design Studio hand-edit — crop, straighten, tune, sharpen, vignette.

    The Designer's manual tools run on a canvas in the browser (so sliders are
    immediate), then post the flattened image here with a summary of what they
    changed. It becomes a new version in the image's thread, exactly like an AI
    edit, so it stays revertible and flows into the approval gate and the export.
    """
    brief = _designer_brief(db, brief_id, user)
    data = await file.read()
    try:
        img, msg = banner_image_service.apply_manual_edit(
            db, brief, image_id, data, file.content_type or "", summary, user
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BannerCommentResult(
        image=BannerImageOut.model_validate(img),
        message=BannerImageMessageOut.model_validate(msg),
    )


@router.get("/banner-images/{image_id}/messages", response_model=list[BannerImageMessageOut])
def list_banner_image_messages(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BannerImageMessageOut]:
    """The Designer's chat thread for one hero image (base version, then each edit)."""
    _designer_brief(db, brief_id, user)
    img = banner_image_service.get_image(db, brief_id, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    banner_image_service.ensure_seed(db, img)  # always surface the original as version 1
    return [
        BannerImageMessageOut.model_validate(m)
        for m in banner_image_service.list_messages(db, image_id)
    ]


@router.get("/banner-images/{image_id}/messages/{message_id}/content")
def banner_image_message_content(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    message_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the PNG bytes of one version in the chat thread (scroll-back history)."""
    _designer_brief(db, brief_id, user)
    msg = banner_image_service.get_message(db, brief_id, image_id, message_id)
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return Response(content=msg.data, media_type=msg.mime_type)


@router.post("/banner-images/{image_id}/comment", response_model=BannerCommentResult)
async def comment_banner_image(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    comment: str = Form(...),
    from_message_id: uuid.UUID | None = Form(None),
    references: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerCommentResult:
    """Refine a hero image with a chat comment — edits the image and logs the turn.

    Multipart rather than JSON because the Designer can attach reference images to
    the turn ("make it look like this"). They're used for this one edit and not
    stored: the version they produce is the thing worth keeping.
    """
    brief = _designer_brief(db, brief_id, user)
    attached = [(await f.read(), f.content_type or "") for f in references]
    try:
        banner_image_service.validate_references(attached)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    try:
        img, msg = banner_image_service.add_comment(
            db, brief, image_id, comment, user, from_message_id, attached
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return BannerCommentResult(
        image=BannerImageOut.model_validate(img),
        message=BannerImageMessageOut.model_validate(msg),
    )


@router.post("/banner-images/{image_id}/messages/{message_id}/select", response_model=BannerImageOut)
def select_banner_image_version(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    message_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerImageOut:
    """Make a thread version the live one (what the card and Figma export use)."""
    brief = _designer_brief(db, brief_id, user)
    try:
        img = banner_image_service.select_version(db, brief, image_id, message_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return BannerImageOut.model_validate(img)


@router.post("/banner-images/approve", response_model=list[BannerImageOut])
def approve_banner_images(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BannerImageOut]:
    """Approve the current set of hero images — the gate before Figma export."""
    brief = _designer_brief(db, brief_id, user)
    try:
        images = banner_image_service.approve_images(db, brief, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return [BannerImageOut.model_validate(i) for i in images]


@router.post("/figma-export", response_model=FigmaExportResult)
def figma_export(
    brief_id: uuid.UUID,
    payload: FigmaExportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FigmaExportResult:
    """Create a Figma file named by the Designer and export the approved banners."""
    brief = _designer_brief(db, brief_id, user)
    try:
        result = figma_export_service.export_to_figma(
            db,
            brief,
            user,
            payload.file_name,
            # Render with the template the Designer picked for this brief unless the
            # request names another, so the banners match the hero art-direction.
            template_id=payload.template_id or brief.banner_template_id,
            sizes=payload.sizes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except FigmaAuthError as e:
        logger.warning("Figma export auth failure for brief %s: %s", brief_id, e)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except FigmaMCPError as e:
        logger.exception("Figma export MCP failure for brief %s", brief_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return FigmaExportResult(**result)


@router.post("/design/submit-for-review", response_model=BriefOut)
def submit_design_for_review(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Send the Figma-exported design to the Marketing Lead for creative review —
    the Designer's explicit final action, once they've reviewed the exported file."""
    brief = _designer_brief(db, brief_id, user)
    try:
        brief = banner_image_service.submit_for_review(db, brief, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BriefOut.model_validate(brief)
