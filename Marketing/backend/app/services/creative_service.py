"""Copy generation — turn a submitted brief into structured ad copies.

Runs while the brief is with the Copywriter. Builds a context prompt from the
brief, asks the AI seam (ADK Copy Agent) for copies, and persists them.
Regenerating replaces the prior set. (Rows are still stored as `Creative`.)
"""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.banner_image import BannerImage, BannerImageStatus
from app.models.brief import Brief, BriefStage
from app.models.brief_event import BriefEventKind
from app.models.creative import Creative
from app.models.creative_version import CreativeVersion
from app.models.user import User
from app.schemas.creative import CreativeEditOne, DesignHandoffRequest
from app.services import ai_log_service, assignment_service, brief_service
from app.services import agent_prompt_service
from app.services.ai_service import get_ai_service
from app.services.brief_fields import fields_for
from app.services.brief_service import _record


# Fields carried on the brief but withheld from the Copy Agent: internal routing
# detail (the owner's name has no place in ad copy) and links the agent cannot
# open — it runs with an output_schema, so it has no tool use.
_CONTEXT_OMIT = frozenset({"owner_name", "sm_final_ui_screen", "sm_samples_references"})


def _brief_context(brief: Brief) -> str:
    """Assemble the brief into a prompt for the Creative Agent.

    Driven by the same field catalog as the Brief Creator's extraction schema, so
    everything the author filled in reaches the agent and a field added to a brief
    doesn't have to be wired up here a second time. Blank fields are skipped —
    the agent sees the brief that was written, not a form full of holes.
    """
    lines = [f"Brief type: {brief.brief_type}"]
    for key, label in fields_for(brief.brief_type):
        if key in _CONTEXT_OMIT:
            continue
        value = getattr(brief, key)
        text = str(value).strip() if value is not None else ""
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


_VERSION_FIELDS = ("visual_reference", "headline", "body", "cta", "entity_attribution", "terms")


def _snapshot(creative: Creative, label: str, actor: User | None, model_version: str) -> CreativeVersion:
    """A CreativeVersion capturing the creative's current copy."""
    return CreativeVersion(
        creative_id=creative.id,
        label=label,
        editor_id=actor.id if actor else None,
        editor_name=actor.full_name if actor else None,
        model_version=model_version,
        **{f: getattr(creative, f) for f in _VERSION_FIELDS},
    )


def _apply_version(creative: Creative, version: CreativeVersion) -> None:
    """Mirror a version's copy onto the creative row (what approvals / export read)."""
    for f in _VERSION_FIELDS:
        setattr(creative, f, getattr(version, f))
    creative.active_version = version


def ensure_versioned(db: Session, creative: Creative) -> Creative:
    """Backfill a base version for creatives that predate versioning, so every
    creative always has at least one selectable version. No-op otherwise."""
    if creative.versions:
        return creative
    base = _snapshot(creative, "Generated", None, creative.model_version)
    db.add(base)
    db.flush()
    creative.active_version = base
    db.commit()
    db.refresh(creative)
    return creative


def list_versions(db: Session, creative: Creative) -> list[CreativeVersion]:
    ensure_versioned(db, creative)
    return list(creative.versions)


def edit_creative(
    db: Session, creative: Creative, edit: CreativeEditOne, actor: User
) -> Creative:
    """Save an edit as a new version and make it live."""
    ensure_versioned(db, creative)
    version = CreativeVersion(
        creative_id=creative.id,
        label="Edited",
        editor_id=actor.id,
        editor_name=actor.full_name,
        model_version="manual",
        visual_reference=(edit.visual_reference or "").strip() or None,
        headline=edit.headline.strip(),
        body=edit.body.strip(),
        cta=edit.cta.strip() or "Learn More",
        entity_attribution=(edit.entity_attribution or "").strip() or None,
        terms=(edit.terms or "").strip() or None,
    )
    db.add(version)
    db.flush()
    _apply_version(creative, version)
    db.commit()
    db.refresh(creative)
    return creative


def select_version(db: Session, creative: Creative, version_id: uuid.UUID) -> Creative:
    """Make a prior version live — mirrors its copy back onto the creative."""
    ensure_versioned(db, creative)
    version = next((v for v in creative.versions if v.id == version_id), None)
    if version is None:
        raise ValueError("version not found")
    _apply_version(creative, version)
    db.commit()
    db.refresh(creative)
    return creative


def generate_creatives(db: Session, brief: Brief, actor: User, count: int) -> list[Creative]:
    """Generate and persist a fresh set of creatives for the brief."""
    prompt = (
        f"Generate exactly {count} distinct ad creatives for this campaign.\n\n"
        f"{_brief_context(brief)}"
    )
    # Copy direction, widest first: the runner's standing (master) prompt, then
    # this brief's own — see agent_prompt_service.resolve_copy_direction.
    append = agent_prompt_service.resolve_copy_direction(
        db, actor_id=actor.id, brief_prompt=brief.copy_prompt
    )
    result = get_ai_service().generate_creatives(prompt, count, prompt_append=append)

    # Replace any prior set so regeneration is clean.
    for old in list(brief.creatives):
        db.delete(old)
    db.flush()

    created: list[Creative] = []
    for i, c in enumerate(result.creatives):
        creative = Creative(
            brief_id=brief.id,
            position=i,
            visual_reference=(c.get("visual_reference") or None),
            headline=(c.get("headline") or "").strip(),
            body=(c.get("body") or "").strip(),
            cta=(c.get("cta") or "").strip() or "Learn More",
            entity_attribution=(c.get("entity_attribution") or None),
            terms=(c.get("terms") or None),
            model_version=result.model_version,
        )
        db.add(creative)
        created.append(creative)

    # Seed each creative's version history with its generated base, made live.
    db.flush()
    for creative in created:
        base = _snapshot(creative, "Generated", actor, result.model_version)
        db.add(base)
        db.flush()
        creative.active_version = base

    _record(
        db,
        brief,
        actor,
        BriefEventKind.creatives_generated,
        f"Generated {len(created)} creative{'s' if len(created) != 1 else ''} "
        f"({result.model_version})",
    )
    ai_log_service.record_call(
        db,
        operation="copy_generation",
        model=result.model_version,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        latency_ms=result.usage.latency_ms,
        brief_id=brief.id,
        actor_id=actor.id,
        commit=False,
    )
    db.commit()
    for c in created:
        db.refresh(c)
    return created


def submit_copies_for_approval(
    db: Session, brief: Brief, actor: User, payload: DesignHandoffRequest
) -> Brief:
    """Persist the Copywriter's edits to the copies, auto-route the Designer to
    the admin-configured default, then hand the brief to design. The Copywriter
    doesn't pick the Designer; the default holder can reassign afterwards. One
    atomic save-and-handoff. Raises DefaultAssigneeError if no default Designer is
    configured. (The Marketing Lead, assigned at brief submit, will review the
    finished design; that checkpoint is re-opened here.)"""
    designer = assignment_service.require_default(db, "DS")
    brief.designer_id = designer.id

    by_id = {c.id: c for c in brief.creatives}
    updates = payload.creatives
    for u in updates:
        c = by_id.get(u.id)
        if c is None:
            continue  # ignore unknown ids — only this brief's copies are editable
        c.visual_reference = (u.visual_reference or "").strip() or None
        c.headline = u.headline.strip()
        c.body = u.body.strip()
        c.cta = u.cta.strip() or "Learn More"
        c.entity_attribution = (u.entity_attribution or "").strip() or None
        c.terms = (u.terms or "").strip() or None

    brief.stage = BriefStage.design.value
    brief_service._reset_checkpoint(brief, "creative_review")
    _record(
        db,
        brief,
        actor,
        BriefEventKind.copies_submitted,
        f"Submitted {len(brief.creatives)} cop"
        f"{'ies' if len(brief.creatives) != 1 else 'y'} — handed to the Designer",
    )
    _record(
        db, brief, actor, BriefEventKind.assigned,
        f"Routed to the Designer ({designer.full_name})",
    )
    db.commit()
    db.refresh(brief)
    return brief


def list_design_queue(db: Session, designer: User) -> list[tuple[Brief, int, int, int]]:
    """Briefs assigned to this Designer (stage = design), each with its creative
    count and banner-image progress: (brief, creatives, images, approved_images).

    Creative and BannerImage are both fanned out from Brief, so the counts use
    COUNT(DISTINCT ...) to avoid the join's cartesian inflation."""
    creative_count = func.count(func.distinct(Creative.id))
    image_count = func.count(func.distinct(BannerImage.id))
    approved_count = func.count(
        func.distinct(
            case((BannerImage.status == BannerImageStatus.approved.value, BannerImage.id))
        )
    )
    rows = db.execute(
        select(Brief, creative_count, image_count, approved_count)
        .outerjoin(Creative, Creative.brief_id == Brief.id)
        .outerjoin(BannerImage, BannerImage.brief_id == Brief.id)
        .where(Brief.stage == BriefStage.design.value, Brief.designer_id == designer.id)
        .group_by(Brief.id)
        .order_by(Brief.updated_at.asc())
    ).all()
    return [(brief, cc, ic, ac) for brief, cc, ic, ac in rows]


def list_creatives(db: Session, brief_id: uuid.UUID) -> list[Creative]:
    return list(
        db.execute(
            select(Creative).where(Creative.brief_id == brief_id).order_by(Creative.position)
        ).scalars()
    )


def list_copywriting_queue(db: Session, copywriter: User) -> list[tuple[Brief, int]]:
    """Briefs assigned to this Copywriter and awaiting copy (stage = copywriting),
    each with how many copies it already has (0 = nothing written yet)."""
    rows = db.execute(
        select(Brief, func.count(Creative.id))
        .outerjoin(Creative, Creative.brief_id == Brief.id)
        .where(
            Brief.stage == BriefStage.copywriting.value,
            Brief.copywriter_id == copywriter.id,
        )
        .group_by(Brief.id)
        .order_by(Brief.submitted_at.asc())
    ).all()
    return [(brief, count) for brief, count in rows]
