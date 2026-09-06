"""Outbound email notifications.

Every meaningful brief state change funnels through ``brief_service._record``;
this module turns those events into personalized, on-brand emails.

Two distinct trails per brief:

* **Notifications** — plain status updates. One conversation per brief
  (subject ``GenAIForge · {title}``), sent to everyone involved so the whole
  pipeline stays transparent.
* **Approvals** — sign-off requests with Approve / Request-changes buttons.
  Their own conversation (subject ``Approval needed: {title}``) so they never
  get buried under status updates.

Per brief event we send at most **one** mail per distinct email address: the
approval mail if that address holds a pending approval lane, otherwise the
notification. Both carry the same transparency block — a horizontal pipeline
stepper plus a top-to-bottom "who does what" list with names, so anyone can see
the whole chain and whose turn it is.

Sending is fire-and-forget on a small thread pool so a slow or failing SMTP
server never blocks — or breaks — the request that triggered the event.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.brief import Brief, BriefStage, Gate1State
from app.models.brief_event import BriefEventKind
from app.models.user import User
from app.services import approval_links
from app.services.notification_service import title_for

logger = logging.getLogger(__name__)

# Sends run off the request path. A handful of workers is plenty for one mailbox.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email")

# ── GenAIForge Marketing palette ─────────────────────────────────────────────
_INK = "#0B0C10"       # header band, headlines
_BRONZE = "#B8956C"    # primary CTA, accents
_PURPLE = "#6D17CE"    # secondary — current step highlight
_SKY = "#1CBABA"       # done step, accents
_BODY_INK = "#161a26"
_MUTED = "#8a8f9e"
_GREY_LINE = "#d7dbe3"
_HOLLOW = "#cfd3dd"
_FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Full role names for greetings / context lines.
ROLE_TITLES: dict[str, str] = {
    "CW": "Copywriter",
    "ML": "Marketing Lead",
    "PL": "Product Lead",
    "DS": "Designer",
    "AD": "Admin",
}

# Pure-internal generation steps — no email (they'd fire before anything is
# actually ready for another participant to act on). Every other kind emails.
_SKIP_KINDS = {
    BriefEventKind.creatives_generated.value,
    BriefEventKind.banner_images_generated.value,
    # A Design Studio hand-edit is mid-production iteration — the Designer may save
    # several in a row, and nobody else can act until the design is sent for review.
    BriefEventKind.banner_image_edited.value,
    # Editing/discarding a draft is the author's own housekeeping, logged for the
    # audit trail but not something anyone else needs an email about.
    BriefEventKind.edited.value,
    BriefEventKind.deleted.value,
    # Attaching/removing a sample reference image is part of filling the brief —
    # logged for the audit trail, but not an email-worthy event on its own.
    BriefEventKind.reference_added.value,
    BriefEventKind.reference_removed.value,
}

# Brief column holding each pipeline slot's assignee.
_SLOT_COLUMN: dict[str, str] = {
    "creator": "creator_id",
    "copywriter": "copywriter_id",
    "marketing": "marketing_id",
    "product": "product_id",
    "designer": "designer_id",
}

# The linear pipeline, in order — drives the horizontal stepper: (stage, label,
# owner slot). "completed" sits past the end (everything done).
_PIPELINE: list[tuple[str, str, str]] = [
    (BriefStage.draft.value, "Draft", "creator"),
    (BriefStage.brief_review.value, "Brief review", "marketing"),
    (BriefStage.copywriting.value, "Copywriting", "copywriter"),
    (BriefStage.design.value, "Design", "designer"),
    (BriefStage.creative_review.value, "Creative review", "marketing"),
    (BriefStage.final_signoff.value, "Sign-off", "product"),
]

# The sequential approval checkpoints, keyed by the stage they're actionable at:
# (owner slot, state column prefix, title).
_CHECKPOINTS: dict[str, tuple[str, str, str]] = {
    BriefStage.brief_review.value: ("marketing", "brief_review", "Brief review"),
    BriefStage.creative_review.value: ("marketing", "creative_review", "Creative review"),
    BriefStage.final_signoff.value: ("product", "final_signoff", "Final sign-off"),
}


@dataclass
class _Outbound:
    to_addr: str
    to_name: str
    subject: str
    html: str
    text: str
    # Stable Message-ID this mail references (threads it). None for standalone
    # mail (OTP, invite) that shouldn't thread into a brief conversation.
    thread_root: str | None = None


# ── Threading roots ──────────────────────────────────────────────────────────
def _domain() -> str:
    return settings.email.from_address.rpartition("@")[2] or "genaiforge.local"


def _thread_root(brief: Brief) -> str:
    """Stable synthetic Message-ID for a brief's *notification* trail. Never sent
    as a real message — it only needs to be identical across the brief's mails."""
    return f"<brief-{brief.id}@{_domain()}>"


def _approval_thread_root(brief: Brief) -> str:
    """Separate root for a brief's *approval* trail, so sign-off requests thread
    on their own — apart from the status updates."""
    return f"<brief-{brief.id}-approval@{_domain()}>"


# ── Small helpers ────────────────────────────────────────────────────────────
def _role_title(role: str) -> str:
    return ROLE_TITLES.get(role, role)


def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0] or "there"


def _brief_title(brief: Brief) -> str:
    return (brief.project_name or brief.product_name or "Untitled brief").strip()


def _stage_index(brief: Brief) -> int:
    """Index of the brief's current pipeline stage (``len(_PIPELINE)`` once the
    final sign-off is in — i.e. everything complete)."""
    if brief.stage == BriefStage.completed.value or brief.status == "approved":
        return len(_PIPELINE)
    for i, (stage, _label, _slot) in enumerate(_PIPELINE):
        if brief.stage == stage:
            return i
    return 0


def _cta(kind: str, recipient_role: str) -> str:
    """A short, role-aware line telling the recipient what this means for them."""
    K = BriefEventKind
    if kind in (K.submitted.value, K.assigned.value):
        if recipient_role == "ML":
            return "The brief is in your queue — review it, then approve or request changes."
        if recipient_role == "CW":
            return "The brief is now in your queue for copywriting."
        if recipient_role == "DS":
            return "The copies are ready — the brief is in your queue for design."
        if recipient_role == "PL":
            return "The design is approved — your final sign-off is needed."
        return "There's movement on this brief."
    if kind == K.copies_submitted.value:
        if recipient_role == "DS":
            return "The copies have been handed off — the brief is ready for design."
        return "The copies have been handed off to the Designer."
    if kind == K.gate1_signoff.value:
        return "An approval checkpoint has been decided; see where the brief stands below."
    if kind == K.gate1_cleared.value:
        return "Final sign-off is complete — this brief is good to go."
    if kind == K.changes_requested.value:
        return "Changes were requested — please review the notes and revise."
    if kind == K.approved.value:
        return "The brief has been approved."
    if kind == K.banner_images_approved.value:
        return "The banner images have been approved."
    if kind == K.design_submitted.value:
        if recipient_role == "ML":
            return "The design is ready — your creative review is needed."
        return "The design has been submitted for creative review."
    if kind == K.figma_exported.value:
        if recipient_role == "ML":
            return "The banners are ready — your creative review is needed."
        return "The banners have been exported to Figma and sent for review."
    if kind == K.created.value:
        return "A new brief has been created."
    return "There's an update on this brief."


# ── Roster + slot resolution ─────────────────────────────────────────────────
def _load_roster(db: Session, brief: Brief) -> dict[str, User | None]:
    """slot → User for every pipeline slot on the brief (names for the
    transparency block). Includes inactive users so history still reads."""
    ids = {getattr(brief, col) for col in _SLOT_COLUMN.values()}
    ids.discard(None)
    users: dict[uuid.UUID, User] = {}
    if ids:
        users = {u.id: u for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}
    return {slot: users.get(getattr(brief, col)) for slot, col in _SLOT_COLUMN.items()}


def _slots_for_ids(brief: Brief, ids: set[uuid.UUID]) -> set[str]:
    """Which pipeline slots the given user ids occupy on this brief."""
    return {slot for slot, col in _SLOT_COLUMN.items() if getattr(brief, col) in ids}


def _pending_approval_slots(brief: Brief, slots: set[str]) -> set[str]:
    """The slot the recipient can act on right now: the owner of the brief's
    current approval checkpoint, if it's still pending and they hold it."""
    cp = _CHECKPOINTS.get(brief.stage)
    if cp is None:
        return set()
    slot, prefix, _title = cp
    if slot in slots and getattr(brief, f"{prefix}_state") == Gate1State.pending.value:
        return {slot}
    return set()


# ── Stepper / status-bar building blocks ─────────────────────────────────────
def _circle(kind: str) -> str:
    """A stepper node dot. done → filled sky with a tick; current → filled purple;
    changes → amber with '!'; upcoming → hollow grey."""
    if kind == "done":
        return (f'<div style="width:26px;height:26px;border-radius:50%;background:{_SKY};'
                'margin:0 auto;text-align:center;line-height:26px;color:#fff;font-size:13px;'
                'font-weight:700;">&#10003;</div>')
    if kind == "current":
        return (f'<div style="width:26px;height:26px;border-radius:50%;background:{_PURPLE};'
                f'border:2px solid {_PURPLE};margin:0 auto;font-size:0;line-height:0;">&nbsp;</div>')
    if kind == "changes":
        return ('<div style="width:26px;height:26px;border-radius:50%;background:#e3b23c;'
                'margin:0 auto;text-align:center;line-height:26px;color:#5a3a00;font-size:15px;'
                'font-weight:700;">!</div>')
    return (f'<div style="width:26px;height:26px;border-radius:50%;background:#fff;'
            f'border:2px solid {_HOLLOW};margin:0 auto;font-size:0;line-height:0;">&nbsp;</div>')


def _step_cell(width: str, left: str, circle: str, right: str, label: str) -> str:
    """One node of a horizontal stepper: connecting line, circle, line, label."""
    return (
        f'<td width="{width}" valign="top">'
        '<table role="presentation" width="100%" style="border-collapse:collapse;"><tr>'
        f'<td style="font-size:0;line-height:0;" valign="middle"><div style="height:3px;background:{left};font-size:0;line-height:0;">&nbsp;</div></td>'
        f'<td width="30" style="width:30px;" valign="middle">{circle}</td>'
        f'<td style="font-size:0;line-height:0;" valign="middle"><div style="height:3px;background:{right};font-size:0;line-height:0;">&nbsp;</div></td>'
        f'</tr></table>{label}</td>'
    )


def _pipeline_stepper_html(brief: Brief) -> str:
    """Horizontal pipeline stepper — done nodes filled sky with a tick, the
    current node purple, upcoming hollow, and the connecting line filled
    left-to-right as the brief advances."""
    cur = _stage_index(brief)
    n = len(_PIPELINE)
    width = f"{100 / n:.4f}%"
    cells = ""
    for i, (_stage, label, _slot) in enumerate(_PIPELINE):
        done = cur >= n or i < cur
        current = i == cur and cur < n
        circle = _circle("done" if done else "current" if current else "upcoming")
        left = "transparent" if i == 0 else (_SKY if (cur >= n or i <= cur) else _GREY_LINE)
        right = "transparent" if i == n - 1 else (_SKY if (cur >= n or i < cur) else _GREY_LINE)
        color = _SKY if done else (_PURPLE if current else "#a7abb8")
        weight = "800" if current else "600"
        lbl = (f'<div style="text-align:center;margin-top:8px;font-size:10px;'
               f'font-weight:{weight};color:{color};">{label}</div>')
        cells += _step_cell(width, left, circle, right, lbl)
    return (
        f'<p style="margin:0 0 8px;font-size:11px;color:{_MUTED};text-transform:uppercase;'
        'letter-spacing:1px;font-weight:600;">Where the brief is</p>'
        '<table role="presentation" width="100%" style="border-collapse:collapse;'
        f'table-layout:fixed;margin:0 0 26px;"><tr>{cells}</tr></table>'
    )


def _vdot(kind: str) -> str:
    if kind == "done":
        return (f'<div style="width:11px;height:11px;border-radius:50%;background:{_SKY};'
                'margin:4px auto 0;font-size:0;line-height:0;">&nbsp;</div>')
    if kind == "current":
        return (f'<div style="width:13px;height:13px;border-radius:50%;background:#fff;'
                f'border:3px solid {_PURPLE};margin:3px auto 0;font-size:0;line-height:0;">&nbsp;</div>')
    return (f'<div style="width:11px;height:11px;border-radius:50%;background:#fff;'
            f'border:2px solid {_HOLLOW};margin:4px auto 0;font-size:0;line-height:0;">&nbsp;</div>')


_STAGE_CHIP = {
    "done": ("DONE", _SKY),
    "current": ("IN PROGRESS", _PURPLE),
    "upcoming": ("WAITING", "#a7abb8"),
}


def _wdw_row(stage_label: str, slot: str, state: str, roster: dict[str, User | None],
             my_slots: set[str], last: bool = False) -> str:
    """One row of the top-to-bottom 'who does what' list: dot, stage + owner
    name/role, status chip."""
    user = roster.get(slot)
    owner = user.full_name if user else "To be assigned"
    role = _role_title(user.role) if user else ""
    label = f"{owner} ({role})" if role else owner
    is_me = slot in my_slots
    if is_me:
        owner_html = f'<span style="color:{_PURPLE};font-weight:600;"> · {label} · you</span>'
    else:
        owner_html = f'<span style="color:#9aa0ae;font-weight:500;"> · {label}</span>'
    text, color = _STAGE_CHIP[state]
    pad = "0" if last else "0 0 16px"
    return (
        f'<tr><td style="width:22px;vertical-align:top;padding:0;">{_vdot(state)}</td>'
        f'<td style="padding:{pad};"><div style="font-weight:600;color:{_BODY_INK};">{stage_label}{owner_html}</div></td>'
        f'<td style="padding:{pad};text-align:right;white-space:nowrap;vertical-align:top;">'
        f'<span style="font-size:11px;font-weight:700;color:{color};">{text}</span></td></tr>'
    )


def _who_does_what_html(brief: Brief, roster: dict[str, User | None], my_slots: set[str]) -> str:
    """Top-to-bottom list of every pipeline stage with the person responsible and
    their status."""
    idx = _stage_index(brief)
    n = len(_PIPELINE)
    rows = ""
    for i, (_stage, label, slot) in enumerate(_PIPELINE):
        state = "done" if (idx >= n or i < idx) else ("current" if i == idx else "upcoming")
        rows += _wdw_row(label, slot, state, roster, my_slots, last=(i == n - 1))
    return (
        f'<p style="margin:0 0 12px;font-size:11px;color:{_MUTED};text-transform:uppercase;'
        'letter-spacing:1px;font-weight:600;">Who does what</p>'
        '<table role="presentation" width="100%" style="border-collapse:collapse;'
        f'font-size:14px;margin:0 0 6px;">{rows}</table>'
    )


# What the owner of each stage is waiting to do.
_STAGE_ACTION: dict[str, str] = {
    BriefStage.draft.value: "submit the brief",
    BriefStage.brief_review.value: "review & approve the brief",
    BriefStage.copywriting.value: "write the copies",
    BriefStage.design.value: "produce the banners",
    BriefStage.creative_review.value: "review the design",
    BriefStage.final_signoff.value: "give the final sign-off",
}


def _awaiting(brief: Brief, roster: dict[str, User | None]) -> tuple[str, str]:
    """(plain, html-inner) one-liner naming who acts next."""
    idx = _stage_index(brief)
    if idx >= len(_PIPELINE):
        done = "Complete — the brief has been signed off."
        return (done, done)
    _stage, _label, slot = _PIPELINE[idx]
    u = roster.get(slot)
    who = u.full_name if u else "the assignee"
    action = _STAGE_ACTION.get(brief.stage, "act on the brief")
    return (f"Awaiting: {who} to {action}.",
            f"Awaiting: <strong>{who}</strong> to {action}.")


def _status_text(brief: Brief) -> str:
    """Plain-text pipeline with the current stage bracketed."""
    cur = _stage_index(brief)
    parts = []
    for i, (_stage, label, _slot) in enumerate(_PIPELINE):
        parts.append(f"[{label}]" if i == cur and cur < len(_PIPELINE) else label)
    return " > ".join(parts)


# ── HTML shell ───────────────────────────────────────────────────────────────
def _shell(inner: str, footer_note: str) -> str:
    return f"""\
<!doctype html><html><body style="margin:0;background:#f4f5f7;padding:24px;font-family:{_FONT};color:{_BODY_INK};">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e7e8ec;border-radius:16px;overflow:hidden;">
    <div style="background:{_INK};padding:20px 24px;">
      <div style="color:#D4B896;font-weight:800;font-size:17px;letter-spacing:-.2px;">GenAIForge</div>
      <div style="color:#B8956C;font-size:11px;letter-spacing:1.4px;text-transform:uppercase;margin-top:2px;">Marketing</div>
    </div>
    <div style="padding:24px;">{inner}</div>
    <div style="padding:16px 24px;border-top:1px solid #eef0f3;font-size:12px;color:#a7abb8;">
      {footer_note}<br>GenAIForge Marketing.
    </div>
  </div>
</body></html>"""


def _eyebrow(text: str, color: str) -> str:
    return (f'<p style="margin:0 0 4px;font-size:12px;color:{color};text-transform:uppercase;'
            f'letter-spacing:1px;font-weight:700;">{text}</p>')


def _headline(title: str) -> str:
    return (f'<h1 style="margin:0 0 16px;font-size:21px;line-height:1.25;letter-spacing:-.01em;'
            f'color:{_INK};">{title}</h1>')


# ── Renderers ────────────────────────────────────────────────────────────────
def _note_label(kind: str) -> str:
    """What the actor's note *is*, for the recipient. On a change request it's the
    whole point of the mail, so it gets named as such."""
    if kind == BriefEventKind.changes_requested.value:
        return "What needs to change"
    return "Note"


def _note_html(kind: str, note: str | None) -> str:
    """The actor's note, quoted. Amber for a change request (it's an action), grey
    otherwise. Empty string when there's no note."""
    note = (note or "").strip()
    if not note:
        return ""
    changes = kind == BriefEventKind.changes_requested.value
    edge, bg = ("#e3b23c", "#fffaf0") if changes else (_GREY_LINE, "#f7f8fa")
    body = escape(note).replace("\n", "<br>")
    return (
        f'<p style="margin:0 0 8px;font-size:11px;color:{_MUTED};text-transform:uppercase;'
        f'letter-spacing:1px;font-weight:600;">{_note_label(kind)}</p>'
        f'<blockquote style="margin:0 0 24px;font-size:15px;line-height:1.6;color:{_BODY_INK};'
        f'background:{bg};border-left:3px solid {edge};padding:12px 14px;'
        f'border-radius:0 8px 8px 0;">{body}</blockquote>'
    )


def _note_text(kind: str, note: str | None) -> str:
    note = (note or "").strip()
    if not note:
        return ""
    quoted = "\n".join(f"  {line}" for line in note.splitlines())
    return f"{_note_label(kind)}:\n{quoted}\n\n"


def _render_notification(
    brief: Brief, kind: str, action: str, actor: User,
    roster: dict[str, User | None], to_addr: str, to_name: str,
    recipient_role: str, my_slots: set[str], note: str | None = None,
) -> _Outbound:
    title = _brief_title(brief)
    headline = title_for(kind)
    actor_role = _role_title(actor.role)
    cta = _cta(kind, recipient_role)
    link = f"{settings.email.app_base_url.rstrip('/')}/briefs/{brief.id}"
    await_text, await_html = _awaiting(brief, roster)

    inner = (
        _eyebrow(headline, _SKY)
        + _headline(title)
        + f'<p style="margin:0 0 14px;font-size:15px;">Hi {_first_name(to_name)},</p>'
        + f'<p style="margin:0 0 18px;font-size:15px;"><strong>{actor.full_name}</strong> '
          f'({actor_role}) {action.rstrip(".").lower()}.</p>'
        + f'<p style="margin:0 0 24px;font-size:15px;background:#f2fbfb;border-left:3px solid {_SKY};'
          f'padding:12px 14px;border-radius:0 8px 8px 0;">{cta}</p>'
        + _note_html(kind, note)
        + _pipeline_stepper_html(brief)
        + _who_does_what_html(brief, roster, my_slots)
        + f'<p style="margin:18px 0 24px;font-size:13px;color:#3a3f4d;background:#f5f5f6;'
          f'border-radius:8px;padding:11px 14px;">{await_html}</p>'
        + f'<a href="{link}" style="display:inline-block;background:{_PURPLE};color:#fff;'
          'text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:10px;">'
          'Open the brief &rarr;</a>'
    )
    footer = "You're receiving this because you're involved in this brief."

    text = (
        f"Hi {_first_name(to_name)},\n\n"
        f"{headline} on the brief “{title}”.\n"
        f"{actor.full_name} ({actor_role}) {action.rstrip('.').lower()}.\n\n"
        f"{cta}\n\n"
        f"{_note_text(kind, note)}"
        f"Progress: {_status_text(brief)}\n"
        f"{await_text}\n\n"
        f"Open the brief: {link}\n\n"
        f"— GenAIForge Marketing"
    )

    return _Outbound(
        to_addr=to_addr, to_name=to_name,
        subject=f"GenAIForge · {title}",
        html=_shell(inner, footer), text=text,
        thread_root=_thread_root(brief),
    )


def _action_buttons_html(brief: Brief, pending_slots: set[str], roster: dict[str, User | None]) -> str:
    """Approve / Request-changes button pair for the brief's current checkpoint,
    if this address holds it and it's pending."""
    cp = _CHECKPOINTS.get(brief.stage)
    if cp is None:
        return ""
    slot, _prefix, title = cp
    if slot not in pending_slots or not roster.get(slot):
        return ""
    user = roster[slot]
    approve_url, changes_url = approval_links.action_urls(str(brief.id), str(user.id))
    block = (
        f'<div style="font-size:12px;color:{_MUTED};font-weight:600;margin:2px 0 8px;">{title}</div>'
        + '<div style="margin:0 0 12px;">'
        + f'<a href="{approve_url}" style="display:inline-block;background:{_PURPLE};color:#fff;'
          'text-decoration:none;font-weight:700;font-size:14px;padding:12px 22px;border-radius:10px;'
          'margin:0 10px 0 0;">Approve</a>'
        + f'<a href="{changes_url}" style="display:inline-block;background:#fff;color:#8a5a00;'
          'border:1.5px solid #e3b23c;text-decoration:none;font-weight:700;font-size:14px;'
          'padding:11px 20px;border-radius:10px;">Request changes</a>'
        + '</div>'
    )
    return (
        f'<p style="margin:0 0 10px;font-size:11px;color:{_MUTED};text-transform:uppercase;'
        'letter-spacing:1px;font-weight:600;">Act from your inbox</p>'
        f'<div style="margin:0 0 14px;">{block}</div>'
    )


def _render_approval(
    brief: Brief, actor: User, roster: dict[str, User | None],
    to_addr: str, to_name: str, pending_slots: set[str], my_slots: set[str],
) -> _Outbound:
    title = _brief_title(brief)
    link = f"{settings.email.app_base_url.rstrip('/')}/briefs/{brief.id}"

    cp = _CHECKPOINTS.get(brief.stage)
    cp_title = cp[2] if cp else "approval"

    inner = (
        _eyebrow("Your approval is requested", _PURPLE)
        + _headline(title)
        + f'<p style="margin:0 0 14px;font-size:15px;">Hi {_first_name(to_name)},</p>'
        + f'<p style="margin:0 0 18px;font-size:15px;">The brief “{title}” has reached the '
          f'<strong>{cp_title}</strong> checkpoint. Your review is needed to move it forward.</p>'
        + _action_buttons_html(brief, pending_slots, roster)
        + _pipeline_stepper_html(brief)
        + _who_does_what_html(brief, roster, my_slots)
        + f'<p style="margin:22px 0 0;font-size:12px;color:#a7abb8;">Prefer the full view? '
          f'<a href="{link}" style="color:{_PURPLE};text-decoration:none;font-weight:600;">'
          'Open the brief &rarr;</a></p>'
    )
    footer = "You're receiving this as an approver on this brief."

    approve_lines = ""
    if cp and roster.get(cp[0]):
        a, c = approval_links.action_urls(str(brief.id), str(roster[cp[0]].id))
        approve_lines = f"Approve: {a}\nRequest changes: {c}\n"

    text = (
        f"Hi {_first_name(to_name)},\n\n"
        f"The brief “{title}” has reached the {cp_title} checkpoint. "
        f"Your approval is requested.\n\n"
        f"{approve_lines}\n"
        f"Progress: {_status_text(brief)}\n\n"
        f"Open the brief: {link}\n\n"
        f"— GenAIForge Marketing"
    )

    return _Outbound(
        to_addr=to_addr, to_name=to_name,
        subject=f"Approval needed: {title}",
        html=_shell(inner, footer), text=text,
        thread_root=_approval_thread_root(brief),
    )


# ── Invite ───────────────────────────────────────────────────────────────────
_INVITE_HIGHLIGHTS: dict[str, list[str]] = {
    "CW": [
        "Turn every approved brief routed to you into clear, on-brand copy.",
        "Hand your copies straight to the Designer when they're ready.",
        "Follow each brief from draft through to sign-off, in real time.",
    ],
    "ML": [
        "Review and approve each new brief before copywriting begins.",
        "Approve the finished design, or request changes — in one click.",
        "See the whole pipeline, from draft to final sign-off.",
    ],
    "PL": [
        "Author briefs and send them for Marketing review.",
        "Give the final 'good to go' once the design is approved.",
        "Track every brief end to end.",
    ],
    "DS": [
        "Pick up briefs with approved copy and produce the hero banners.",
        "Generate on-brand visuals and export straight to Figma for review.",
        "See the full context and copy behind every brief.",
    ],
    "AD": [
        "Set the default owner for each role in the pipeline.",
        "Invite teammates and manage their access.",
        "Oversee every brief as it moves from draft to sign-off.",
    ],
}
_INVITE_FALLBACK = [
    "Pick up the briefs routed to you and move them forward.",
    "Collaborate with the rest of the team in one place.",
    "Follow every brief from draft through to design.",
]


def _render_invite(user: User, actor: User) -> _Outbound:
    """Welcome email for a freshly created account: role overview and sign-in link."""
    role_title = _role_title(user.role)
    first = _first_name(user.full_name)
    link = settings.email.app_base_url.rstrip("/") + "/"
    highlights = _INVITE_HIGHLIGHTS.get(user.role, _INVITE_FALLBACK)

    dots = [_SKY, _BRONZE]
    hi_rows = ""
    for i, line in enumerate(highlights):
        last = i == len(highlights) - 1
        pad = "0" if last else "0 0 14px"
        hi_rows += (
            f'<tr><td width="26" valign="top" style="padding:{pad};">'
            f'<div style="width:8px;height:8px;border-radius:50%;background:{dots[i % 2]};'
            'margin:6px auto 0;font-size:0;line-height:0;">&nbsp;</div></td>'
            f'<td style="padding:{pad};font-size:14px;line-height:1.5;color:#3a3f4d;">{line}</td></tr>'
        )

    html = f"""\
<!doctype html><html><body style="margin:0;background:#f4f5f7;padding:24px;font-family:{_FONT};color:{_BODY_INK};">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e7e8ec;border-radius:16px;overflow:hidden;">
    <div style="background:{_INK};background-image:linear-gradient(135deg,{_INK} 0%,#1a1c24 58%,{_BRONZE} 125%);padding:34px 28px 30px;">
      <div style="color:#D4B896;font-weight:800;font-size:22px;letter-spacing:-.3px;">GenAIForge</div>
      <div style="color:#B8956C;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin-top:4px;">Marketing</div>
      <div style="height:1px;background:rgba(255,255,255,.16);margin:20px 0 18px;font-size:0;line-height:0;">&nbsp;</div>
      <div style="color:#D4B896;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">You're invited</div>
      <div style="color:#ffffff;font-size:25px;font-weight:800;line-height:1.2;letter-spacing:-.01em;margin-top:7px;">Welcome aboard, {first}.</div>
    </div>
    <div style="padding:26px 28px;">
      <p style="margin:0 0 20px;font-size:15px;line-height:1.55;"><strong>{actor.full_name}</strong> has set up your account on GenAIForge Marketing as a <strong>{role_title}</strong>. Here's what you'll do here:</p>
      <table role="presentation" width="100%" style="border-collapse:collapse;margin:0 0 26px;">{hi_rows}</table>
      <p style="margin:0 0 10px;font-size:11px;color:{_MUTED};text-transform:uppercase;letter-spacing:1px;font-weight:600;">How to sign in</p>
      <table role="presentation" width="100%" style="border-collapse:collapse;font-size:14px;margin:0 0 24px;background:#faf7f2;border:1px solid #e8dcc8;border-radius:12px;">
        <tr><td style="padding:14px 16px;color:{_MUTED};width:150px;">Your account</td><td style="padding:14px 16px;font-weight:700;color:{_INK};">{user.email}</td></tr>
      </table>
      <a href="{link}" style="display:inline-block;background:{_BRONZE};color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:13px 26px;border-radius:10px;">Sign in &rarr;</a>
      <p style="margin:20px 0 0;font-size:13px;color:#a7abb8;">Ask an admin for your password if you don't have one yet, then sign in with your email.</p>
    </div>
    <div style="padding:16px 28px;border-top:1px solid #eef0f3;font-size:12px;color:#a7abb8;">
      GenAIForge Marketing.
    </div>
  </div>
</body></html>"""

    text = (
        f"Hi {first},\n\n"
        f"{actor.full_name} has set up your account on GenAIForge Marketing "
        f"as a {role_title}.\n\n"
        "Here's what you'll do here:\n"
        + "".join(f"  - {line}\n" for line in highlights)
        + f"\nYour account: {user.email}\n"
        "Ask an admin for your password if you don't have one yet, then sign in with your email.\n\n"
        f"Sign in: {link}\n\n"
        "— GenAIForge Marketing"
    )

    return _Outbound(
        to_addr=user.email, to_name=user.full_name,
        subject="[GenAIForge] Welcome to GenAIForge Marketing",
        html=html, text=text,
    )


# ── OTP ──────────────────────────────────────────────────────────────────────
def send_approval_otp(
    *, to_addr: str, to_name: str, otp: str, brief_title: str, decision_label: str
) -> None:
    """Email a one-time approval code, synchronously. Raises on failure so the
    caller (the approval page) can tell the approver the code couldn't be sent."""
    subject = f"[GenAIForge] Your approval code: {otp}"
    text = (
        f"Hi {_first_name(to_name)},\n\n"
        f"Your one-time code to {decision_label.lower()} the brief “{brief_title}” is:\n\n"
        f"    {otp}\n\n"
        "Enter it on the confirmation page to record your decision. The code expires in 10 minutes.\n"
        "If you didn't request this, you can ignore this email.\n\n"
        "— GenAIForge Marketing"
    )
    inner = (
        f'<p style="margin:0 0 14px;font-size:15px;">Hi {_first_name(to_name)},</p>'
        f'<p style="margin:0 0 14px;font-size:15px;">Your one-time code to '
        f'<strong>{decision_label.lower()}</strong> the brief “{brief_title}”:</p>'
        f'<div style="margin:0 0 18px;font-size:34px;font-weight:800;letter-spacing:8px;'
        f'text-align:center;background:#f2fbfb;border:1px solid #cdeeee;border-radius:12px;'
        f'padding:16px 0;color:{_INK};">{otp}</div>'
        f'<p style="margin:0 0 6px;font-size:13px;color:{_MUTED};">Enter it on the confirmation '
        'page to record your decision. The code expires in 10 minutes.</p>'
        '<p style="margin:0;font-size:13px;color:#a7abb8;">If you didn\'t request this, you can '
        'ignore this email.</p>'
    )
    html = _shell(inner, "This code was requested from the approval page.")
    _send_via_smtp([_Outbound(to_addr=to_addr, to_name=to_name, subject=subject, html=html, text=text)])


# ── Dispatch ─────────────────────────────────────────────────────────────────
def _participants(db: Session, brief: Brief) -> list[User]:
    """Active users involved in this brief, deduped by id — everyone, including
    the actor, so the whole pipeline stays transparent."""
    ids = {getattr(brief, col) for col in _SLOT_COLUMN.values()}
    ids.discard(None)
    if not ids:
        return []
    return list(
        db.execute(select(User).where(User.id.in_(ids), User.is_active.is_(True))).scalars()
    )


def _to_mime(m: _Outbound, from_addr: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = m.subject
    msg["From"] = formataddr((settings.email.from_name, from_addr))
    msg["To"] = formataddr((m.to_name, m.to_addr))
    # A unique Message-ID per mail; thread by pointing at the relevant root.
    msg["Message-ID"] = make_msgid(domain=from_addr.rpartition("@")[2] or None)
    if m.thread_root:
        msg["In-Reply-To"] = m.thread_root
        msg["References"] = m.thread_root
    msg.set_content(m.text)
    msg.add_alternative(m.html, subtype="html")
    return msg


def _send_via_smtp(messages: list[_Outbound]) -> None:
    """One SMTP connection (STARTTLS + App Password), sending every message."""
    with smtplib.SMTP(settings.email.smtp_host, settings.email.smtp_port, timeout=20) as server:
        server.ehlo()
        if settings.email.smtp_use_tls:
            server.starttls()
            server.ehlo()
        if settings.email.smtp_username and settings.email.smtp_password:
            server.login(settings.email.smtp_username, settings.email.smtp_password)
        for m in messages:
            server.send_message(_to_mime(m, settings.email.from_address))


def _send_batch(messages: list[_Outbound]) -> None:
    """Send every message over SMTP. Runs in a worker thread; never raises — a
    mail failure must not break or block the caller."""
    if not messages:
        return
    recipients = ", ".join(m.to_addr for m in messages)
    try:
        _send_via_smtp(messages)
        logger.info("Sent %d email(s) to: %s", len(messages), recipients)
    except Exception:  # never let email break or block the caller
        logger.exception("Failed to send %d email(s) to: %s", len(messages), recipients)


def notify_user_invited(user: User, actor: User) -> None:
    """Email a newly created user a welcome + sign-in link (off the request
    path). Safe to call inside a request; failures are logged, not raised."""
    if not settings.email.enabled:
        logger.info("Email disabled — not sending invite to %s", user.email or "<no email>")
        return
    if not user.email:
        logger.warning("User %s has no email — invite not sent", user.full_name)
        return
    try:
        _executor.submit(_send_batch, [_render_invite(user, actor)])
        logger.info("Queued invite email for %s (%s)", user.email, user.full_name)
    except Exception:
        logger.exception("Failed to prepare invite email for user %s", user.id)


def notify_event(
    db: Session, brief: Brief, kind: str, action: str, actor: User, note: str | None = None
) -> None:
    """Resolve the brief's participants and dispatch one personalized mail per
    distinct address (off the request path) — the approval request if that
    address can act right now, otherwise the status update. `note` is the actor's
    message on the event (a reviewer's change request, a reassignment reason) and
    is quoted in the mail. Safe to call inside a request; failures are logged,
    not raised."""
    if not settings.email.enabled:
        logger.info("Email disabled — not sending '%s' notification for brief %s", kind, brief.id)
        return
    if kind in _SKIP_KINDS:
        return
    try:
        roster = _load_roster(db, brief)
        # Group involved participants by email address — the dedupe. Several
        # pipeline accounts can share one inbox (esp. in UAT); each address gets
        # a single mail per event.
        groups: dict[str, list[User]] = defaultdict(list)
        for user in _participants(db, brief):
            if user.email:
                groups[user.email.strip().lower()].append(user)

        messages: list[_Outbound] = []
        for users in groups.values():
            addr = users[0].email
            to_name = users[0].full_name
            my_slots = _slots_for_ids(brief, {u.id for u in users})
            pending = _pending_approval_slots(brief, my_slots)
            if pending:
                messages.append(_render_approval(brief, actor, roster, addr, to_name, pending, my_slots))
            else:
                messages.append(
                    _render_notification(brief, kind, action, actor, roster, addr, to_name,
                                         users[0].role, my_slots, note)
                )

        if messages:
            logger.info(
                "Queued %d mail(s) for '%s' on brief %s to: %s",
                len(messages), kind, brief.id, ", ".join(m.to_addr for m in messages),
            )
            _executor.submit(_send_batch, messages)
        else:
            logger.info(
                "No email recipients for '%s' on brief %s (no involved participant has an email)",
                kind, brief.id,
            )
    except Exception:
        logger.exception("Failed to prepare notification emails for brief %s", brief.id)
