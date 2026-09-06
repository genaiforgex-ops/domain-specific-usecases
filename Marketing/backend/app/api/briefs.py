"""Brief routes — intake CRUD, the Marketing Lead's brief review, the Copywriter
handoff, and the sequential approval checkpoints (brief review → creative review
→ final sign-off) that carry a brief through to completion."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.brief import Brief, BriefStage, BriefStatus
from app.models.user import User
from app.schemas.brief import (
    ApprovalRequest,
    BriefCreate,
    BriefEventOut,
    BriefExtractRequest,
    BriefExtractResponse,
    BriefInboxItem,
    BriefOut,
    BriefReferenceImageOut,
    BriefSummary,
    BriefUpdate,
    CopyPromptUpdate,
    ReassignRequest,
    RejectRequest,
)
from app.models.creative import Creative
from app.schemas.creative import (
    CreativeEditOne,
    CreativeGenerateRequest,
    CreativeOut,
    CreativeVersionOut,
    DesignHandoffRequest,
    DesignQueueItem,
    GenerationQueueItem,
)
from app.services import (
    ai_log_service,
    assignment_service,
    brief_reference_service,
    brief_service,
    creative_service,
)
from app.adk.agents import AGENT_KIND_BRIEF
from app.services import agent_prompt_service
from app.services.ai_service import get_ai_service

router = APIRouter(prefix="/api/briefs", tags=["briefs"])

# Pipeline owners.
COPYWRITER_ROLE = "CW"
DESIGNER_ROLE = "DS"
ADMIN_ROLE = "AD"
APPROVAL_ROLES = brief_service.APPROVAL_ROLES  # Marketing Lead / Product Lead
# Every internal role can read any brief + its full history (transparency).
# The Product Lead authors briefs and, as an approver, is an internal role too.
_INTERNAL_ROLES = {COPYWRITER_ROLE, *APPROVAL_ROLES, DESIGNER_ROLE, ADMIN_ROLE}
_EDITABLE = {BriefStatus.draft.value, BriefStatus.changes_requested.value}


def _can_view(brief: Brief, user: User) -> bool:
    """Who may read a brief and its timeline: its creator (own briefs) and every
    internal role (full read across the pipeline, at any stage)."""
    return brief.creator_id == user.id or user.role in _INTERNAL_ROLES


def _can_edit(brief: Brief, user: User) -> bool:
    """Who may edit a brief's content: its creator while it's a draft or was
    returned for changes, and the assigned Marketing Lead while reviewing it."""
    if brief.creator_id == user.id and brief.status in _EDITABLE:
        return True
    return (
        user.role == brief_service.MARKETING_ROLE
        and brief.stage == BriefStage.brief_review.value
        and brief.marketing_id == user.id
    )


def _get_owned(db: Session, brief_id: uuid.UUID, user: User) -> Brief:
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your brief")
    return brief


@router.get("", response_model=list[BriefSummary])
def list_my_briefs(
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefSummary]:
    rows = brief_service.list_briefs_for_creator(db, user, q)
    return [BriefSummary.model_validate(b) for b in rows]


@router.get("/all", response_model=list[BriefSummary])
def all_briefs(
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefSummary]:
    """Search briefs the user has worked on — every brief for Admin oversight,
    otherwise only the briefs the user holds a slot on."""
    return [BriefSummary.model_validate(b) for b in brief_service.list_all_briefs(db, user, q)]


@router.get("/copywriting-queue", response_model=list[GenerationQueueItem])
def copywriting_queue(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GenerationQueueItem]:
    """Briefs assigned to this Copywriter and awaiting copy."""
    if user.role != COPYWRITER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Copywriters only")
    return [
        GenerationQueueItem(
            id=b.id,
            brief_type=b.brief_type,
            stage=b.stage,
            project_name=b.project_name,
            product_name=b.product_name,
            owner_name=b.owner_name,
            budget_inr=b.budget_inr,
            creative_count=count,
            updated_at=b.updated_at,
        )
        for b, count in creative_service.list_copywriting_queue(db, user)
    ]


@router.get("/design-queue", response_model=list[DesignQueueItem])
def design_queue(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DesignQueueItem]:
    """Briefs whose copies the Copywriter has handed off — the Designer's queue,
    each carrying its banner-production progress for the dashboard."""
    if user.role != DESIGNER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Designers only")
    return [
        DesignQueueItem(
            id=b.id,
            brief_type=b.brief_type,
            stage=b.stage,
            project_name=b.project_name,
            product_name=b.product_name,
            owner_name=b.owner_name,
            budget_inr=b.budget_inr,
            creative_count=creatives,
            image_count=images,
            approved_count=approved,
            figma_file_url=b.figma_file_url,
            figma_exported_at=b.figma_exported_at,
            updated_at=b.updated_at,
        )
        for b, creatives, images, approved in creative_service.list_design_queue(db, user)
    ]


@router.get("/approval-queue", response_model=list[BriefSummary])
def approval_queue(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefSummary]:
    """Briefs assigned to this approver and awaiting their checkpoint decision."""
    if not brief_service.is_approver(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Marketing Lead or Product Lead only"
        )
    return [BriefSummary.model_validate(b) for b in brief_service.list_approval_queue(db, user)]


@router.get("/inbox", response_model=list[BriefInboxItem])
def my_inbox(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefInboxItem]:
    """Briefs that need the signed-in creator's action right now."""
    return [
        BriefInboxItem(
            id=b.id,
            brief_type=b.brief_type,
            stage=b.stage,
            status=b.status,
            title=b.project_name or b.product_name or "Untitled brief",
            cta=cta,
            priority=priority,
            review_note=b.review_note,
            updated_at=b.updated_at,
        )
        for b, cta, priority in brief_service.inbox_for_creator(db, user)
    ]


@router.get("/audit", response_model=list[BriefEventOut])
def audit_log(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefEventOut]:
    """Immutable, identity-stamped trail of brief events in the user's scope."""
    out: list[BriefEventOut] = []
    for e in brief_service.list_events(db, user):
        entry = BriefEventOut.model_validate(e)
        entry.brief_title = e.brief.project_name or e.brief.product_name or "Untitled brief"
        out.append(entry)
    return out


@router.get("/{brief_id}", response_model=BriefOut)
def get_brief(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    return BriefOut.model_validate(brief)


@router.get("/{brief_id}/events", response_model=list[BriefEventOut])
def brief_events(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefEventOut]:
    """The immutable, identity-stamped activity timeline for one brief — the
    transparency feed shown on the brief detail page. Chronological (oldest first)."""
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    return [BriefEventOut.model_validate(e) for e in brief.events]


@router.post("", response_model=BriefOut, status_code=status.HTTP_201_CREATED)
def create_brief(
    payload: BriefCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    brief = brief_service.create_brief(db, user, payload)
    return BriefOut.model_validate(brief)


@router.post("/extract", response_model=BriefExtractResponse)
def extract_brief(
    payload: BriefExtractRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefExtractResponse:
    if not payload.raw_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="raw_text is required")
    append = agent_prompt_service.resolve_append(db, user.id, AGENT_KIND_BRIEF)
    try:
        result = get_ai_service().extract_brief(
            payload.raw_text, payload.brief_type.value, prompt_append=append
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    ai_log_service.record_call(
        db,
        operation="brief_extract",
        model=result.model_version,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        latency_ms=result.usage.latency_ms,
        actor_id=user.id,
    )
    return BriefExtractResponse(values=result.values, model_version=result.model_version)


@router.patch("/{brief_id}", response_model=BriefOut)
def update_brief(
    brief_id: uuid.UUID,
    payload: BriefUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_edit(brief, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief can't be edited right now",
        )
    brief = brief_service.update_brief(db, brief, payload, user)
    return BriefOut.model_validate(brief)


@router.post("/{brief_id}/submit", response_model=BriefOut)
def submit_brief(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    brief = _get_owned(db, brief_id, user)
    if brief.status not in _EDITABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Brief is already submitted"
        )
    missing = brief_service.missing_required(brief)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete these required fields before submitting: " + ", ".join(missing),
        )
    # The brief auto-routes to the admin-configured default Marketing Lead for
    # review — the creator doesn't pick one.
    try:
        brief = brief_service.submit_brief(db, brief, user)
    except assignment_service.DefaultAssigneeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BriefOut.model_validate(brief)


# ── Approval checkpoints (brief review → creative review → final sign-off) ────


@router.post("/{brief_id}/approval", response_model=BriefOut)
def approval_signoff(
    brief_id: uuid.UUID,
    payload: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Record this approver's decision on the brief's current checkpoint (ML →
    brief review / creative review, PL → final sign-off)."""
    if not brief_service.is_approver(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Marketing Lead or Product Lead only",
        )
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    cp = brief_service.checkpoint_for(brief)
    if cp is None or not assignment_service.holds_role(user, cp.role):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This brief is not awaiting your approval"
        )
    if getattr(brief, cp.assignee_col) != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another approver",
        )
    if payload.action == "request_changes" and not (payload.note and payload.note.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A note is required when requesting changes",
        )
    brief = brief_service.approval_signoff(db, brief, user, payload)
    return BriefOut.model_validate(brief)


# ── Reject — the current work-stage owner sends the brief back a step ─────────


@router.post("/{brief_id}/reject", response_model=BriefOut)
def reject_brief(
    brief_id: uuid.UUID,
    payload: RejectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Send the brief back a step for changes, with a required reason. Available to
    whoever holds the brief at a work stage (Copywriter → author, Designer →
    Copywriter); the approval gates reject through the approval endpoint instead."""
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    step = brief_service.reject_step_for(brief)
    if step is None or user.role != step.role:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief can't be sent back from where it is now",
        )
    if getattr(brief, step.assignee_col) != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another teammate",
        )
    if not payload.note.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A note is required when sending a brief back",
        )
    brief = brief_service.reject_to_previous(db, brief, user, payload.note.strip())
    return BriefOut.model_validate(brief)


# ── Reassignment — hand your current task to a same-role peer ─────────────────


@router.post("/{brief_id}/reassign", response_model=BriefOut)
def reassign_brief(
    brief_id: uuid.UUID,
    payload: ReassignRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Reassign the brief's current-stage task to another active user of the same
    role. The caller must currently hold that task (or be an Admin)."""
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")

    slot = payload.slot or brief_service.default_slot(user.role, brief.stage)
    if slot is None or slot not in brief_service.REASSIGN_SLOTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to reassign for your role at this stage",
        )
    column, role, stage = brief_service.REASSIGN_SLOTS[slot]

    if brief.stage != stage:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief isn't at the stage where that work can be reassigned",
        )

    current = getattr(brief, column)
    if user.role != ADMIN_ROLE and current != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reassign work currently assigned to you",
        )
    if payload.assignee_id == current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That person already holds this brief",
        )
    if not brief_service.valid_assignee(db, payload.assignee_id, role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pick a valid, active teammate in the same role",
        )

    new_user = db.get(User, payload.assignee_id)
    brief = brief_service.reassign(db, brief, user, slot, new_user, payload.note)
    return BriefOut.model_validate(brief)


# ── Copy direction — this brief's own (individual-level) copy prompt ──────────
# The master-level prompts live in the Prompt Studio (see /api/agent-prompts) and
# apply to every generation; this one steers a single brief. Both are folded in at
# generation time by agent_prompt_service.resolve_copy_direction.

# Stages at which the copy direction still changes the outcome — once the copies
# are handed to design, editing it would only mislead.
_COPY_PROMPT_STAGES = {
    BriefStage.draft.value,
    BriefStage.brief_review.value,
    BriefStage.copywriting.value,
}


@router.put("/{brief_id}/copy-prompt", response_model=BriefOut)
def set_copy_prompt(
    brief_id: uuid.UUID,
    payload: CopyPromptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Write this brief's copy direction. The brief's author and any Product Lead
    may set it, up until the copies are handed to design. A blank value clears it,
    leaving the master prompts to run on their own."""
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.creator_id != user.id and user.role != brief_service.PRODUCT_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the brief's author or a Product Lead can set the copy direction",
        )
    if brief.stage not in _COPY_PROMPT_STAGES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The copy direction can't be changed once the copies are with the Designer",
        )
    brief.copy_prompt = (payload.prompt or "").strip() or None
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)


# ── Reference images — the sample copies / examples on the brief ──────────────
# The Product Lead (author) attaches example images while filling the brief; the
# reviewing Marketing Lead may too. Everyone in the chain can see them alongside
# the brief, and the Designer's hero-image generation uses them as visual
# references. Bytes are served from the content endpoint, never inlined in JSON.


@router.get("/{brief_id}/reference-images", response_model=list[BriefReferenceImageOut])
def list_reference_images(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BriefReferenceImageOut]:
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    return [
        BriefReferenceImageOut.model_validate(i)
        for i in brief_reference_service.list_(db, brief_id)
    ]


@router.get("/{brief_id}/reference-images/{image_id}/content")
def reference_image_content(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve one reference image's raw bytes (the thumbnail / full view)."""
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    img = brief_reference_service.get(db, brief_id, image_id)
    if img is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(content=img.data, media_type=img.mime_type)


@router.post("/{brief_id}/reference-images", response_model=BriefReferenceImageOut)
async def upload_reference_image(
    brief_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefReferenceImageOut:
    """Attach a sample/example image to the brief — allowed to whoever may edit the
    brief right now (its author while draft/returned, or the reviewing Marketing
    Lead)."""
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_edit(brief, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief can't be edited right now",
        )
    data = await file.read()
    try:
        img = brief_reference_service.add(
            db, brief, data, file.filename or "reference", caption, user
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BriefReferenceImageOut.model_validate(img)


@router.delete("/{brief_id}/reference-images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference_image(
    brief_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    brief = db.get(Brief, brief_id)
    if brief is None or brief.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_edit(brief, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief can't be edited right now",
        )
    try:
        brief_reference_service.delete(db, brief, image_id, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ── Copies — brief → copy generation (Copy Agent) ─────────────────────────────


@router.get("/{brief_id}/creatives", response_model=list[CreativeOut])
def list_creatives(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreativeOut]:
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    return [CreativeOut.model_validate(c) for c in creative_service.list_creatives(db, brief_id)]


@router.post("/{brief_id}/creatives", response_model=list[CreativeOut])
def generate_creatives(
    brief_id: uuid.UUID,
    payload: CreativeGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreativeOut]:
    """Generate copies from the brief — while it's with the Copywriter."""
    if user.role != COPYWRITER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Copywriters only")
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.stage != BriefStage.copywriting.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Copies can be generated only while the brief is with the Copywriter",
        )
    if brief.copywriter_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another Copywriter",
        )
    try:
        creatives = creative_service.generate_creatives(db, brief, user, payload.count)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [CreativeOut.model_validate(c) for c in creatives]


# ── Per-creative version history (generate → view → edit → select a version) ──


def _writable_creative(
    db: Session, brief_id: uuid.UUID, creative_id: uuid.UUID, user: User
) -> Creative:
    """The creative, guarded for edits: caller is the assigned Copywriter and the
    brief is still at the copywriting stage."""
    if user.role != COPYWRITER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Copywriters only")
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.stage != BriefStage.copywriting.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Copies can be edited only while the brief is with the Copywriter",
        )
    if brief.copywriter_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another Copywriter",
        )
    creative = db.get(Creative, creative_id)
    if creative is None or creative.brief_id != brief.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creative not found")
    return creative


@router.get("/{brief_id}/creatives/{creative_id}/versions", response_model=list[CreativeVersionOut])
def list_creative_versions(
    brief_id: uuid.UUID,
    creative_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreativeVersionOut]:
    """A creative's version history — newest last. Visible to anyone who can read the brief."""
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if not _can_view(brief, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this brief")
    creative = db.get(Creative, creative_id)
    if creative is None or creative.brief_id != brief.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creative not found")
    out: list[CreativeVersionOut] = []
    for v in creative_service.list_versions(db, creative):
        item = CreativeVersionOut.model_validate(v)
        item.is_active = creative.active_version_id == v.id
        out.append(item)
    return out


@router.patch("/{brief_id}/creatives/{creative_id}", response_model=CreativeOut)
def edit_creative(
    brief_id: uuid.UUID,
    creative_id: uuid.UUID,
    payload: CreativeEditOne,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreativeOut:
    """Save an edit to one creative — stored as a new, live version."""
    creative = _writable_creative(db, brief_id, creative_id, user)
    if not payload.headline.strip() or not payload.body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Headline and body are required"
        )
    creative = creative_service.edit_creative(db, creative, payload, user)
    return CreativeOut.model_validate(creative)


@router.post(
    "/{brief_id}/creatives/{creative_id}/versions/{version_id}/select", response_model=CreativeOut
)
def select_creative_version(
    brief_id: uuid.UUID,
    creative_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreativeOut:
    """Make a prior version the live one for this creative."""
    creative = _writable_creative(db, brief_id, creative_id, user)
    try:
        creative = creative_service.select_version(db, creative, version_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found") from e
    return CreativeOut.model_validate(creative)


@router.post("/{brief_id}/creatives/handoff", response_model=BriefOut)
def submit_copies(
    brief_id: uuid.UUID,
    payload: DesignHandoffRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BriefOut:
    """Save the Copywriter's edits to the copies and hand the brief to the Designer
    (stage → design). One atomic 'Save & hand off to design' action."""
    if user.role != COPYWRITER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Copywriters only")
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    if brief.stage != BriefStage.copywriting.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Copies can be submitted only while the brief is with the Copywriter",
        )
    if brief.copywriter_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This brief is assigned to another Copywriter",
        )
    if not brief.creatives:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Write the copies before handing off to design",
        )
    # The Designer auto-routes to the admin-configured default — the Copywriter
    # doesn't pick them.
    try:
        brief = creative_service.submit_copies_for_approval(db, brief, user, payload)
    except assignment_service.DefaultAssigneeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BriefOut.model_validate(brief)


@router.delete("/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brief(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    brief = _get_owned(db, brief_id, user)
    if brief.status not in _EDITABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a draft or returned brief can be deleted",
        )
    brief_service.delete_brief(db, brief, user)
