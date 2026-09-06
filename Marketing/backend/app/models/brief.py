"""Brief model — Small/Medium/Large intake briefs and their approval state.

Per-type fields are kept as their own typed columns. Small and Medium share one
template (the `sm_*` group); Large uses the `lg_*` group. Columns outside a
brief's type stay null. Mandatory-field enforcement happens on submit in the
service, not at the column level, so drafts can be saved partially.
"""

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import UUID, Date, DateTime, ForeignKey, Integer, String, Text, func, or_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BriefType(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"


class BriefStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    changes_requested = "changes_requested"


class BriefStage(str, Enum):
    """Position in the linear pipeline. `status` owns the draft/submitted
    sub-state; `stage` tracks where the brief sits overall.

    Flow: Product Lead authors (draft) → Marketing Lead reviews/approves the brief
    (brief_review) → Copywriter AI-drafts & edits the copies (copywriting) →
    Designer produces the banners in Figma (design) → Marketing Lead approves the
    design (creative_review) → Product Lead gives the final sign-off
    (final_signoff) → done (completed)."""

    draft = "draft"
    brief_review = "brief_review"  # submitted — Marketing Lead reviews & approves the brief
    copywriting = "copywriting"  # brief approved — Copywriter writes & edits the copies
    design = "design"  # copies handed off — Designer produces the banners
    creative_review = "creative_review"  # banners exported — Marketing Lead approves the design
    final_signoff = "final_signoff"  # design approved — Product Lead's final "good to go"
    completed = "completed"  # signed off — pipeline complete


class Gate1State(str, Enum):
    pending = "pending"
    approved = "approved"
    changes_requested = "changes_requested"


class Brief(Base):
    """An intake brief authored by a Brief Creator and sent for approval."""

    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_type: Mapped[str] = mapped_column(String(16), nullable=False)  # BriefType
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=BriefStatus.draft.value)
    stage: Mapped[str] = mapped_column(
        String(24), nullable=False, default=BriefStage.draft.value
    )  # BriefStage — pipeline position
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Task allocation ──────────────────────────────────────────────────────
    # Work auto-routes to admin-configured per-role defaults; each holder may then
    # reassign to a same-role peer. Each stage's queue and write actions are scoped
    # to the assigned person.
    # The Product Lead authors the brief and picks the Copywriter indirectly (auto-
    # routed to the default). The Marketing Lead is assigned on submit (brief +
    # creative review), the Designer at copy hand-off, and the Product Lead approver
    # at creative approval.
    copywriter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    marketing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    designer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Downstream production default ────────────────────────────────────────
    # The banner *category* (e.g. "performance" statics vs "messaging" WhatsApp/RCS/
    # RPN) the Product Lead picks up front, at brief creation. It locks which family
    # of templates the Designer may work from; the Designer still picks the specific
    # template within it. Slug matches banner_templates.category. Nullable so
    # pre-existing briefs fall back to every template downstream.
    banner_category: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # The specific template the *Designer* picks inside that category, before the
    # hero images are generated — it art-directs the photos and renders the export,
    # so it's persisted here rather than held in the browser: a reload, a
    # regenerate and the Figma export all use the same one. NULL until they pick.
    banner_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banner_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Copy direction for THIS brief (the individual-level copy prompt) ─────
    # The Product Lead / brief author's extra instruction for the Copy Agent,
    # scoped to this brief alone. It layers on top of their standing (master)
    # Prompt Studio append — see agent_prompt_service.resolve_copy_direction.
    # NULL / blank → the master prompts run unchanged.
    copy_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Shared identity (all types) ──────────────────────────────────────────
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Both dates are filled by the system, not typed in: brief_date is the day the
    # brief was raised and expected_date is EXPECTED_TURNAROUND_DAYS later. See
    # brief_service.stamp_dates — the single place they're derived.
    brief_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Small / Medium template ──────────────────────────────────────────────
    sm_go_live_timeline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sm_one_line_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_primary_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_business_kpi: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_strategic_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_audience_who: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_audience_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_audience_exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_mandatories_tnc: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_platforms: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_dimensions_specs: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_final_ui_screen: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_samples_references: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Large template ───────────────────────────────────────────────────────
    lg_project_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_business_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_marketing_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_communication_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_effectiveness_metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_ideal_customer: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_demo_age: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lg_demo_gender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lg_demo_top_cities: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lg_goals_motivations: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_category_insight: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_conservative_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_aspirational_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_product_insight: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_key_markets: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_competition: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_product_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_key_features_deliverables: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_unique_offerings: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_think_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_think_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_feel_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_feel_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_do_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_do_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_cultural_sensitivity: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_languages: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_other_considerations: Mapped[str | None] = mapped_column(Text, nullable=True)
    lg_deliverables: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── L1 approval workflow ─────────────────────────────────────────────────
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Campaign budget (display only) ───────────────────────────────────────
    budget_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Approval checkpoints ─────────────────────────────────────────────────
    # Three sequential single-approver gates at different points in the pipeline:
    #   brief_review    — Marketing Lead approves the brief (stage=brief_review)
    #   creative_review — Marketing Lead approves the design (stage=creative_review)
    #   final_signoff   — Product Lead's final "good to go" (stage=final_signoff)
    brief_review_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default=Gate1State.pending.value
    )
    creative_review_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default=Gate1State.pending.value
    )
    final_signoff_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default=Gate1State.pending.value
    )
    brief_review_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    creative_review_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    final_signoff_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    brief_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creative_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    final_signoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Figma export (Designer) ──────────────────────────────────────────────
    # Set once the Designer exports the approved banners into a fresh Figma file.
    figma_file_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    figma_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    figma_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Soft delete ──────────────────────────────────────────────────────────
    # Discarding a draft/returned brief stamps this rather than destroying the row,
    # so the "deleted" audit entry (and the brief's own history) survives and stays
    # visible in the audit log. Every user-facing brief list/detail filters these
    # out; only the audit trail still surfaces them.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])  # noqa: F821
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])  # noqa: F821
    events: Mapped[list["BriefEvent"]] = relationship(  # noqa: F821
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="BriefEvent.at",
    )
    creatives: Mapped[list["Creative"]] = relationship(  # noqa: F821
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="Creative.position",
    )
    # Sample/example images the Product Lead attaches to the brief (oldest first).
    reference_images: Mapped[list["BriefReferenceImage"]] = relationship(  # noqa: F821
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="BriefReferenceImage.created_at",
    )

    @classmethod
    def involves(cls, user_id: uuid.UUID):
        """SQL predicate: this user holds one of the brief's pipeline slots.

        The single definition of "my briefs" — used by both the notification feed
        and the audit trail so the two can never disagree about what a user is
        entitled to see. Role grants nothing on its own; only a slot does.
        """
        return or_(
            cls.creator_id == user_id,
            cls.copywriter_id == user_id,
            cls.marketing_id == user_id,
            cls.product_id == user_id,
            cls.designer_id == user_id,
        )
