"""Brief business logic — drafting, submission (with required-field checks), the
Marketing Lead's brief review, the Copywriter handoff, and the sequential
approval checkpoints (brief review → creative review → final sign-off) that carry
a brief through to completion."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.brief import Brief, BriefStage, BriefStatus, BriefType, Gate1State
from app.models.brief_event import BriefEvent, BriefEventKind
from app.models.user import User
from app.schemas.brief import ApprovalRequest, BriefCreate, BriefUpdate
from app.services import assignment_service, email_service

# Pipeline owners.
COPYWRITER_ROLE = "CW"  # writes the copies
MARKETING_ROLE = "ML"  # reviews the brief + approves the design
PRODUCT_ROLE = "PL"  # authors the brief + gives the final sign-off
DESIGNER_ROLE = "DS"
ADMIN_ROLE = "AD"  # oversight: reads the full audit trail, owns no pipeline stage

# Which Brief column holds the assignee for each role's stage. Queues and write
# actions are scoped to the assigned person.
ASSIGNEE_COLUMN = {
    COPYWRITER_ROLE: "copywriter_id",
    MARKETING_ROLE: "marketing_id",
    PRODUCT_ROLE: "product_id",
    DESIGNER_ROLE: "designer_id",
}


@dataclass(frozen=True)
class Checkpoint:
    """One sequential approval gate: the stage it sits at, the role + assignee
    column that decides it, its state/by/at column prefix, and a display label."""

    stage: str
    role: str
    assignee_col: str
    prefix: str  # e.g. "brief_review" → brief_review_state / _by_id / _at
    label: str


# Keyed by the stage the brief must be in for this checkpoint to be actionable.
CHECKPOINTS: dict[str, Checkpoint] = {
    BriefStage.brief_review.value: Checkpoint(
        BriefStage.brief_review.value, MARKETING_ROLE, "marketing_id", "brief_review", "Brief review"
    ),
    BriefStage.creative_review.value: Checkpoint(
        BriefStage.creative_review.value, MARKETING_ROLE, "marketing_id", "creative_review",
        "Creative review",
    ),
    BriefStage.final_signoff.value: Checkpoint(
        BriefStage.final_signoff.value, PRODUCT_ROLE, "product_id", "final_signoff", "Final sign-off"
    ),
}

# Stages each approver role is responsible for (drives their queue).
APPROVAL_STAGES = {
    MARKETING_ROLE: (BriefStage.brief_review.value, BriefStage.creative_review.value),
    PRODUCT_ROLE: (BriefStage.final_signoff.value,),
}
APPROVAL_ROLES = tuple(APPROVAL_STAGES)


def is_approver(user: User) -> bool:
    """Whether IAM grants ``user`` any approver role (ML or PL). Uses the granted
    role set, not the cached last-active ``User.role`` — a user who holds an
    approver role stays an approver even while acting in another role."""
    return any(assignment_service.holds_role(user, role) for role in APPROVAL_ROLES)


# ── Dates ────────────────────────────────────────────────────────────────────
# Nobody types a date into a brief. The day it was raised is the day it was
# created, and the date it's expected back is a fixed turnaround after that.
EXPECTED_TURNAROUND_DAYS = 3


def stamp_dates(brief: Brief) -> None:
    """Derive the brief's two dates. `brief_date` is the day it was raised (kept
    once set, so an edit doesn't quietly re-date an older brief); `expected_date`
    always follows it by EXPECTED_TURNAROUND_DAYS. The single place either date is
    written — the API accepts no client value for them."""
    if brief.brief_date is None:
        brief.brief_date = date.today()
    brief.expected_date = brief.brief_date + timedelta(days=EXPECTED_TURNAROUND_DAYS)


def _reset_checkpoint(brief: Brief, prefix: str) -> None:
    """Re-open one approval checkpoint (state → pending, clear who/when)."""
    setattr(brief, f"{prefix}_state", Gate1State.pending.value)
    setattr(brief, f"{prefix}_by_id", None)
    setattr(brief, f"{prefix}_at", None)


def valid_assignee(db: Session, user_id: uuid.UUID, role: str) -> bool:
    """True if user_id is an active account IAM grants the expected role."""
    u = db.get(User, user_id)
    return u is not None and u.is_active and assignment_service.holds_role(u, role)


# ── Reassignment ─────────────────────────────────────────────────────────────
# Whoever holds a brief at its current stage can hand it to another active user
# of the same role. Each "slot" maps to (assignee column, role that fills it,
# the stage at which that assignee is the active holder). Roles that act at two
# stages get one slot per stage: the Product Lead authors (`author`) then signs
# off (`product`); the Marketing Lead reviews the brief then the creative.
REASSIGN_SLOTS: dict[str, tuple[str, str, str]] = {
    "author": ("creator_id", PRODUCT_ROLE, BriefStage.draft.value),
    "marketing_brief": ("marketing_id", MARKETING_ROLE, BriefStage.brief_review.value),
    "copywriter": ("copywriter_id", COPYWRITER_ROLE, BriefStage.copywriting.value),
    "designer": ("designer_id", DESIGNER_ROLE, BriefStage.design.value),
    "marketing_creative": ("marketing_id", MARKETING_ROLE, BriefStage.creative_review.value),
    "product": ("product_id", PRODUCT_ROLE, BriefStage.final_signoff.value),
}

_SLOT_LABEL = {
    "author": "authoring",
    "marketing_brief": "Marketing Lead",
    "copywriter": "Copywriter",
    "designer": "Designer",
    "marketing_creative": "Marketing Lead",
    "product": "Product Lead",
}


def default_slot(role: str, stage: str) -> str | None:
    """Which slot a caller reassigns given their role and the brief's stage.
    Returns None when the caller holds no reassignable slot here (e.g. Admin,
    who must name the slot explicitly)."""
    if role == COPYWRITER_ROLE:
        return "copywriter"
    if role == DESIGNER_ROLE:
        return "designer"
    if role == MARKETING_ROLE:
        if stage == BriefStage.brief_review.value:
            return "marketing_brief"
        if stage == BriefStage.creative_review.value:
            return "marketing_creative"
        return None
    if role == PRODUCT_ROLE:
        if stage == BriefStage.draft.value:
            return "author"
        if stage == BriefStage.final_signoff.value:
            return "product"
        return None
    return None


def reassign(
    db: Session, brief: Brief, actor: User, slot: str, new_user: User, note: str | None = None
) -> Brief:
    """Point the slot's assignee column at `new_user` and stamp the trail. The
    caller has already validated the stage, the actor's right to reassign, and
    that `new_user` holds the slot's role."""
    column, _role, _stage = REASSIGN_SLOTS[slot]
    setattr(brief, column, new_user.id)
    _record(
        db,
        brief,
        actor,
        BriefEventKind.assigned,
        f"Reassigned {_SLOT_LABEL[slot]} to {new_user.full_name}",
        note=(note.strip() if note and note.strip() else None),
    )
    db.commit()
    db.refresh(brief)
    return brief

# Fields that must be filled before a brief can be submitted, per type.
# (key, human label) — labels are surfaced verbatim in the 400 detail.
_SMALL_MED_REQUIRED = [
    ("product_name", "Product Name"),
    ("owner_name", "Owner"),
    ("brief_date", "Date"),
    ("sm_go_live_timeline", "Go-live Timeline"),
    ("sm_one_line_summary", "One-line summary"),
    ("sm_primary_goal", "Primary goal"),
    ("sm_audience_who", "Who is this for?"),
    ("sm_audience_segment", "Segment/Cohort specifics"),
    ("sm_mandatories_tnc", "Mandatories and T&C"),
    ("sm_platforms", "Platforms"),
    ("sm_dimensions_specs", "Dimensions & Specifications"),
]

_LARGE_REQUIRED = [
    ("product_name", "Product Name"),
    ("owner_name", "Product Owner"),
    ("brief_date", "Date of Brief Creation"),
    ("lg_marketing_objective", "Marketing Objective"),
    ("lg_communication_objective", "Communication Objective"),
    ("lg_ideal_customer", "Target Audience / Persona"),
    ("lg_product_insight", "Product Insight"),
    ("lg_competition", "Competition"),
    ("lg_product_features", "Products / service features"),
    ("lg_key_features_deliverables", "Key Features/Deliverables"),
    ("lg_unique_offerings", "Unique offerings"),
    ("lg_languages", "Languages"),
    ("lg_deliverables", "Deliverables"),
]


def required_for(brief_type: str) -> list[tuple[str, str]]:
    return _LARGE_REQUIRED if brief_type == BriefType.large.value else _SMALL_MED_REQUIRED


def missing_required(brief: Brief) -> list[str]:
    """Human labels of the required fields still empty for this brief's type."""
    missing = []
    for key, label in required_for(brief.brief_type):
        value = getattr(brief, key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    return missing


def _record(
    db: Session,
    brief: Brief,
    actor: User,
    kind: BriefEventKind,
    action: str,
    note: str | None = None,
) -> None:
    """Append one immutable entry to the brief's audit trail, and email the
    brief's participants about it. Caller commits."""
    db.add(
        BriefEvent(
            brief_id=brief.id,
            kind=kind.value,
            action=action,
            actor_id=actor.id,
            actor_name=actor.full_name,
            actor_role=actor.role,
            note=note,
        )
    )
    # Fire-and-forget personalized emails to the brief's participants. Never
    # raises — a mail failure must not break the state change. The note travels
    # with it: on a change request it *is* the message.
    email_service.notify_event(db, brief, kind.value, action, actor, note=note)


def create_brief(db: Session, creator: User, payload: BriefCreate) -> Brief:
    data = payload.model_dump()
    data["brief_type"] = payload.brief_type.value
    brief = Brief(
        **data,
        creator_id=creator.id,
        status=BriefStatus.draft.value,
        stage=BriefStage.draft.value,
    )
    stamp_dates(brief)
    db.add(brief)
    db.flush()  # assign brief.id before stamping the event
    _record(db, brief, creator, BriefEventKind.created, "Created the brief")
    db.commit()
    db.refresh(brief)
    return brief


def update_brief(db: Session, brief: Brief, payload: BriefUpdate, actor: User) -> Brief:
    """Save an edit to a brief's content and record it on the audit trail.

    Only fields that actually changed value are counted — the form re-sends every
    field on save, so without this a no-op "Save draft" would log a phantom edit.
    The event carries no email (see email_service._SKIP_KINDS): an edit is the
    author's own housekeeping, not a hand-off anyone else must act on.
    """
    changed = 0
    for key, value in payload.model_dump(exclude_unset=True).items():
        if getattr(brief, key) != value:
            setattr(brief, key, value)
            changed += 1
    stamp_dates(brief)  # re-derive, so a client can't hand-set either date
    if changed:
        _record(
            db,
            brief,
            actor,
            BriefEventKind.edited,
            f"Edited the brief ({changed} field{'s' if changed != 1 else ''})",
        )
    db.commit()
    db.refresh(brief)
    return brief


def submit_brief(db: Session, brief: Brief, actor: User) -> Brief:
    """Submit the brief to the default Marketing Lead for review. The creator
    doesn't pick who: it auto-routes to the admin-configured default Marketing
    Lead, who can reassign it (or edit and approve it) afterwards. Raises
    DefaultAssigneeError if no default Marketing Lead is configured."""
    marketing = assignment_service.require_default(db, MARKETING_ROLE)
    resubmit = brief.status == BriefStatus.changes_requested.value
    brief.status = BriefStatus.submitted.value
    brief.stage = BriefStage.brief_review.value
    brief.submitted_at = datetime.now(timezone.utc)
    brief.review_note = None
    brief.reviewer_id = None
    brief.reviewed_at = None
    brief.marketing_id = marketing.id
    _reset_checkpoint(brief, "brief_review")
    _record(
        db,
        brief,
        actor,
        BriefEventKind.submitted,
        "Resubmitted after changes" if resubmit else "Submitted for Marketing review",
    )
    _record(
        db, brief, actor, BriefEventKind.assigned,
        f"Routed to the Marketing Lead ({marketing.full_name})",
    )
    db.commit()
    db.refresh(brief)
    return brief


def delete_brief(db: Session, brief: Brief, actor: User) -> None:
    """Discard a brief — a soft delete.

    The row is stamped ``deleted_at`` rather than destroyed, so the "deleted"
    audit entry (and the brief's whole history) survives and stays visible in the
    audit log. Every user-facing brief list/detail filters ``deleted_at`` out, so
    the brief disappears from the app exactly as a hard delete would.
    """
    brief.deleted_at = datetime.now(timezone.utc)
    _record(db, brief, actor, BriefEventKind.deleted, "Deleted the brief")
    db.commit()


def list_briefs_for_creator(db: Session, creator: User, q: str | None = None) -> list[Brief]:
    stmt = select(Brief).where(Brief.creator_id == creator.id, Brief.deleted_at.is_(None))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Brief.project_name.ilike(like),
                Brief.product_name.ilike(like),
                Brief.owner_name.ilike(like),
            )
        )
    return list(db.execute(stmt.order_by(Brief.updated_at.desc())).scalars())


def list_all_briefs(db: Session, user: User, q: str | None = None) -> list[Brief]:
    """Briefs this user may search, newest first.

    Admin gets every brief in the pipeline — the oversight view. Everyone else is
    scoped to the briefs they hold a slot on (Brief.involves), i.e. the things
    they've actually worked on, not the whole pipeline. Optional free-text match
    over name, product and owner.
    """
    stmt = select(Brief).where(Brief.deleted_at.is_(None))
    if user.role != ADMIN_ROLE:
        stmt = stmt.where(Brief.involves(user.id))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Brief.project_name.ilike(like),
                Brief.product_name.ilike(like),
                Brief.owner_name.ilike(like),
            )
        )
    return list(db.execute(stmt.order_by(Brief.updated_at.desc())).scalars())


# ── Approval checkpoints (brief review → creative review → final sign-off) ────


def checkpoint_for(brief: Brief) -> Checkpoint | None:
    """The approval checkpoint actionable at the brief's current stage, if any."""
    return CHECKPOINTS.get(brief.stage)


def list_approval_queue(db: Session, approver: User) -> list[Brief]:
    """Briefs awaiting this approver — those at one of their checkpoint stages and
    assigned to them (ML → brief_review/creative_review, PL → final_signoff).

    Keyed on the roles IAM grants, not the cached last-active ``User.role``, so a
    user who holds both approver roles sees every checkpoint they own regardless
    of which role they're currently acting in."""
    clauses = [
        and_(Brief.stage == stage, getattr(Brief, ASSIGNEE_COLUMN[role]) == approver.id)
        for role in APPROVAL_ROLES
        if assignment_service.holds_role(approver, role)
        for stage in APPROVAL_STAGES[role]
    ]
    if not clauses:
        return []
    return list(
        db.execute(
            select(Brief)
            .where(or_(*clauses), Brief.deleted_at.is_(None))
            .order_by(Brief.updated_at.asc())
        ).scalars()
    )


def approval_signoff(db: Session, brief: Brief, actor: User, payload: ApprovalRequest) -> Brief:
    """Record the decision on the checkpoint actionable at the brief's current
    stage, then advance the brief (approve) or bounce it back (request changes).

    - brief_review    → copywriting (approve) / back to the author (changes)
    - creative_review → final_signoff (approve) / back to the Designer (changes)
    - final_signoff   → completed (approve) / back to the Designer (changes)
    """
    cp = checkpoint_for(brief)
    if cp is None:
        raise ValueError("This brief is not at an approval checkpoint")
    approved = payload.action == "approve"
    now = datetime.now(timezone.utc)

    state = (Gate1State.approved if approved else Gate1State.changes_requested).value
    setattr(brief, f"{cp.prefix}_state", state)
    setattr(brief, f"{cp.prefix}_by_id", actor.id)
    setattr(brief, f"{cp.prefix}_at", now)

    if approved:
        _record(
            db,
            brief,
            actor,
            BriefEventKind.gate1_signoff,
            f"{cp.label} — approved",
            note=payload.note,
        )
        _advance_after_approval(db, brief, actor, cp)
    else:
        # Bounce *before* recording: `_record` renders the outbound mail from the
        # brief as it stands, so the reviewer's feedback has to reach whoever the
        # brief just landed back on — with the right stage, owner and next action.
        # Its own event kind (not gate1_signoff) is what gives the mail the
        # "Changes requested" headline and the revise-and-resubmit call to action.
        _bounce_after_changes(brief, cp, payload.note)
        _record(
            db,
            brief,
            actor,
            BriefEventKind.changes_requested,
            f"{cp.label} — changes requested",
            note=payload.note,
        )

    db.commit()
    db.refresh(brief)
    return brief


def _advance_after_approval(db: Session, brief: Brief, actor: User, cp: Checkpoint) -> None:
    """Move the brief forward when a checkpoint is approved."""
    if cp.stage == BriefStage.brief_review.value:
        copywriter = assignment_service.require_default(db, COPYWRITER_ROLE)
        brief.copywriter_id = copywriter.id
        brief.review_note = None
        brief.stage = BriefStage.copywriting.value
        _record(
            db, brief, actor, BriefEventKind.assigned,
            f"Brief approved → routed to the Copywriter ({copywriter.full_name})",
        )
    elif cp.stage == BriefStage.creative_review.value:
        # Final sign-off goes back to the brief's author — the Product Lead who
        # raised it — rather than an admin-configured default. They own the brief
        # end to end, so they give it its own final sign-off.
        author = db.get(User, brief.creator_id)
        brief.product_id = brief.creator_id
        brief.review_note = None
        brief.stage = BriefStage.final_signoff.value
        author_name = author.full_name if author else "the author"
        _record(
            db, brief, actor, BriefEventKind.assigned,
            f"Design approved → routed to the author ({author_name}) for final sign-off",
        )
    elif cp.stage == BriefStage.final_signoff.value:
        brief.status = BriefStatus.approved.value
        brief.stage = BriefStage.completed.value
        _record(
            db, brief, actor, BriefEventKind.gate1_cleared,
            "Final sign-off complete — good to go.",
        )


def _bounce_after_changes(brief: Brief, cp: Checkpoint, note: str | None) -> None:
    """Send the brief back when a checkpoint requests changes."""
    brief.review_note = note
    if cp.stage == BriefStage.brief_review.value:
        # Back to the author (Product Lead) to revise and resubmit.
        brief.status = BriefStatus.changes_requested.value
        brief.stage = BriefStage.draft.value
    else:
        # Creative or final rejection → back to the Designer to rework; the design
        # will need re-review, so re-open both post-design checkpoints.
        brief.stage = BriefStage.design.value
        _reset_checkpoint(brief, "creative_review")
        _reset_checkpoint(brief, "final_signoff")


# ── Reject from a work stage — send the brief back a step for changes ─────────
# The approval gates (brief review / creative review / final sign-off) already
# reject via ``approval_signoff``. These cover the two *work* stages, so the
# person actually doing the work can also bounce a brief back when what they were
# handed isn't good enough — the Copywriter to the author, the Designer to the
# Copywriter.


@dataclass(frozen=True)
class RejectStep:
    """A work stage whose current owner may reject the brief back a step.

    ``stage`` is the stage the brief must be in; ``role``/``assignee_col`` identify
    who holds it; ``to_stage`` (with an optional ``to_status`` override) is where a
    rejection sends the brief for changes. ``label`` names the rejected stage on
    the audit trail."""

    stage: str
    role: str
    assignee_col: str
    label: str
    to_stage: str
    to_status: str | None = None


# Keyed by the stage the brief must be in for its owner to reject it.
REJECTS: dict[str, RejectStep] = {
    BriefStage.copywriting.value: RejectStep(
        BriefStage.copywriting.value, COPYWRITER_ROLE, "copywriter_id", "Copywriting",
        # Back to the author (Product Lead) to fix the brief and resubmit — the same
        # place a brief-review rejection lands.
        BriefStage.draft.value, BriefStatus.changes_requested.value,
    ),
    BriefStage.design.value: RejectStep(
        BriefStage.design.value, DESIGNER_ROLE, "designer_id", "Design",
        # Back to the Copywriter to rework the copies and hand off again.
        BriefStage.copywriting.value,
    ),
}


def reject_step_for(brief: Brief) -> RejectStep | None:
    """The reject step available at the brief's current stage, if any."""
    return REJECTS.get(brief.stage)


def reject_to_previous(db: Session, brief: Brief, actor: User, note: str) -> Brief:
    """Send the brief back one step for changes, carrying the actor's reason.

    Used by the work-stage owners (Copywriter → author, Designer → Copywriter);
    the approval gates reject through ``approval_signoff``. The caller has already
    validated the stage, the actor's role and that they hold the brief."""
    step = REJECTS[brief.stage]
    brief.review_note = note
    brief.stage = step.to_stage
    if step.to_status is not None:
        brief.status = step.to_status
    _record(
        db,
        brief,
        actor,
        BriefEventKind.changes_requested,
        f"{step.label} — sent back for changes",
        note=note,
    )
    db.commit()
    db.refresh(brief)
    return brief


class ApprovalLinkError(Exception):
    """The email approval link can't be acted on (expired, wrong stage, already
    decided, …). Carries a user-facing message for the landing page."""


def resolve_link_action(db: Session, brief_id: uuid.UUID, approver_id: uuid.UUID) -> tuple[Brief, User, str]:
    """Validate an email approval link and return (brief, approver, checkpoint_label).

    Raises ApprovalLinkError with a friendly message if the link can no longer be
    acted on — the brief moved on, was reassigned, or the checkpoint was decided."""
    approver = db.get(User, approver_id)
    if approver is None or not approver.is_active:
        raise ApprovalLinkError("This approval link's account is no longer active.")
    brief = db.get(Brief, brief_id)
    if brief is None:
        raise ApprovalLinkError("This brief no longer exists.")
    cp = checkpoint_for(brief)
    if cp is None:
        raise ApprovalLinkError("This brief is no longer awaiting your approval.")
    # Authorize against the role IAM actually grants, not User.role — that column
    # is only a cache of the *last-active* role, so a multi-role approver acting
    # in another role (or an IAM order that made another role active) would else
    # be wrongly refused their own pending checkpoint from the email link.
    if not assignment_service.holds_role(approver, cp.role):
        raise ApprovalLinkError("This account is no longer an approver.")
    if getattr(brief, cp.assignee_col) != approver.id:
        raise ApprovalLinkError("This brief is now assigned to another approver.")
    if getattr(brief, f"{cp.prefix}_state") != Gate1State.pending.value:
        raise ApprovalLinkError("This checkpoint has already been decided on this brief.")
    return brief, approver, cp.label


def decide_from_link(
    db: Session, brief_id: uuid.UUID, approver_id: uuid.UUID, action: str, note: str | None
) -> Brief:
    """Record an approval decision arriving from an email link. Re-validates the
    link (state may have changed since the email was sent), then routes through
    the normal ``approval_signoff`` so events + status emails fire as usual."""
    brief, approver, _label = resolve_link_action(db, brief_id, approver_id)
    if action == "request_changes" and not (note and note.strip()):
        raise ApprovalLinkError("A note is required when requesting changes.")
    payload = ApprovalRequest(action=action, note=(note.strip() if note else None))
    return approval_signoff(db, brief, approver, payload)


# What a brief needs from its creator now, by status. Drafts and bounced-back
# briefs are actionable; submitted/approved ones are waiting elsewhere.
_INBOX_CTA = {
    BriefStatus.draft.value: ("Finish draft & submit", "normal"),
    BriefStatus.changes_requested.value: ("Changes requested — revise & resubmit", "high"),
}


def inbox_for_creator(db: Session, creator: User) -> list[tuple[Brief, str, str]]:
    """Actionable briefs for the creator: (brief, cta, priority), high priority first."""
    rows = db.execute(
        select(Brief)
        .where(
            Brief.creator_id == creator.id,
            Brief.status.in_(list(_INBOX_CTA)),
            Brief.deleted_at.is_(None),
        )
        .order_by(Brief.updated_at.desc())
    ).scalars()
    items = [(b, *_INBOX_CTA[b.status]) for b in rows]
    items.sort(key=lambda t: 0 if t[2] == "high" else 1)
    return items


def list_events(db: Session, user: User) -> list[BriefEvent]:
    """Audit entries this user may read, newest first.

    Admin gets the complete trail — the audit log is an oversight surface, and an
    Admin who can only see their own actions can't audit anything. Everyone else is
    scoped to the events they personally performed (BriefEvent.actor_id): a user
    sees only the things they have done, not the full activity of every brief they
    hold a slot on.
    """
    stmt = (
        select(BriefEvent)
        .join(Brief, BriefEvent.brief_id == Brief.id)
        .options(selectinload(BriefEvent.brief))
    )
    if user.role != ADMIN_ROLE:
        stmt = stmt.where(BriefEvent.actor_id == user.id)
    return list(db.execute(stmt.order_by(BriefEvent.at.desc())).scalars())
