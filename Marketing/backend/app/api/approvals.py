"""Email approval links — the pages an approver lands on when they click
Approve / Request changes straight from a notification email.

These routes are intentionally unauthenticated: the link itself carries a
short-lived HMAC-signed token identifying the brief + approver. Clicking a
button lands on a small branded confirmation page (GET); confirming it POSTs
back and records the decision through the normal approval path (which fires the
usual status emails). No login, and no accidental one-click approvals from email
scanners/prefetchers.
"""

from __future__ import annotations

import html
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.approval_otp import ApprovalOtp
from app.services import approval_links, brief_service, email_service
from app.services.approval_links import verify_token

_OTP_TTL_SEC = 600  # a one-time code is valid for 10 minutes
# Wrong guesses allowed per issued code. A 6-digit code is only 10^6 wide, so an
# unbounded 10-minute window is brute-forceable; five tries makes a guess worth
# ~5-in-a-million and forces the attacker back through the approver's inbox.
_MAX_OTP_ATTEMPTS = 5

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

_VALID_DECISIONS = {"approve", "request_changes"}
_DECISION_LABEL = {"approve": "Approve", "request_changes": "Request changes"}


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _page(inner: str, *, status_code: int = 200) -> HTMLResponse:
    """Wrap page content in the shared GenAIForge Marketing shell."""
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GenAIForge Marketing — Approval</title></head>
<body style="margin:0;background:#f4f5f7;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1d24;">
  <div style="max-width:560px;margin:40px auto;background:#fff;border:1px solid #e7e8ec;border-radius:16px;overflow:hidden;">
    <div style="background:#0B0C10;padding:18px 24px;color:#D4B896;font-weight:700;font-size:15px;letter-spacing:.3px;">GenAIForge&nbsp;Marketing</div>
    <div style="padding:24px;">{inner}</div>
  </div>
</body></html>"""
    return HTMLResponse(content=doc, status_code=status_code)


def _message_page(heading: str, message: str, *, status_code: int = 200) -> HTMLResponse:
    inner = (
        '<p style="margin:0 0 4px;font-size:13px;color:#8a8a93;text-transform:uppercase;letter-spacing:.5px;">Approval</p>'
        f'<h1 style="margin:0 0 16px;font-size:20px;">{_esc(heading)}</h1>'
        f'<p style="margin:0 0 8px;font-size:15px;">{_esc(message)}</p>'
        '<p style="margin:16px 0 0;font-size:14px;color:#8a8a93;">You can close this tab, or open GenAIForge Marketing for the full brief.</p>'
    )
    return _page(inner, status_code=status_code)


def _brief_summary_html(brief) -> str:
    title = brief.project_name or brief.product_name or "Untitled brief"
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:0 0 22px;">'
        f'<tr><td style="padding:6px 0;color:#8a8a93;width:130px;">Brief</td><td style="padding:6px 0;">{_esc(title)}</td></tr>'
        f'<tr><td style="padding:6px 0;color:#8a8a93;">Product</td><td style="padding:6px 0;">{_esc(brief.product_name or "—")}</td></tr>'
        f'<tr><td style="padding:6px 0;color:#8a8a93;">Expected by</td><td style="padding:6px 0;">{_esc(brief.expected_date or "—")}</td></tr>'
        "</table>"
    )


def _decode(token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """(brief_id, approver_id) from a valid token, or None if invalid/expired."""
    try:
        payload = verify_token(token)
        return uuid.UUID(payload["brief_id"]), uuid.UUID(payload["approver_id"])
    except (ValueError, KeyError, TypeError):
        return None


def _otp_form_html(
    otp_token: str,
    decision: str,
    *,
    lane: str | None = None,
    masked_email: str | None = None,
    brief=None,
    error: str | None = None,
) -> str:
    """The OTP-entry form: a 6-digit code field (+ a required note when requesting
    changes). Rendered fresh on the first request and again on a wrong code."""
    approving = decision == "approve"
    btn_color = "#15803d" if approving else "#b45309"
    error_banner = (
        f'<p style="margin:0 0 16px;font-size:14px;color:#b91c1c;background:#fef2f2;'
        f'border:1px solid #fecaca;border-radius:8px;padding:10px 12px;">{_esc(error)}</p>'
        if error
        else ""
    )
    sent_line = (
        f'<p style="margin:0 0 16px;font-size:14px;color:#444;">We emailed a 6-digit code to '
        f"<strong>{_esc(masked_email)}</strong>. Enter it below to {_esc(_DECISION_LABEL[decision].lower())}."
        "</p>"
        if masked_email
        else '<p style="margin:0 0 16px;font-size:14px;color:#444;">Enter the 6-digit code we emailed you.</p>'
    )
    note_field = (
        ""
        if approving
        else (
            '<label style="display:block;margin:0 0 6px;font-size:13px;color:#8a8a93;">Note (required)</label>'
            '<textarea name="note" required rows="4" style="width:100%;box-sizing:border-box;'
            "border:1px solid #d8d9de;border-radius:10px;padding:10px 12px;font-size:14px;"
            'font-family:inherit;margin:0 0 16px;resize:vertical;" placeholder="What needs to change?"></textarea>'
        )
    )
    lane_kicker = (
        f'<p style="margin:0 0 4px;font-size:13px;color:#8a8a93;text-transform:uppercase;letter-spacing:.5px;">{_esc(lane)} approval</p>'
        if lane
        else ""
    )
    return (
        f"{lane_kicker}"
        f'<h1 style="margin:0 0 16px;font-size:20px;">Confirm: {_esc(_DECISION_LABEL[decision])}</h1>'
        f"{error_banner}{sent_line}"
        f"{_brief_summary_html(brief) if brief is not None else ''}"
        '<form method="post" action="/api/approvals/action">'
        f'<input type="hidden" name="otp_token" value="{_esc(otp_token)}">'
        '<input type="text" name="otp" inputmode="numeric" autocomplete="one-time-code" '
        'pattern="[0-9]{6}" maxlength="6" required placeholder="123456" '
        'style="width:100%;box-sizing:border-box;border:1px solid #d8d9de;border-radius:10px;'
        'padding:12px 14px;font-size:22px;letter-spacing:6px;text-align:center;margin:0 0 16px;">'
        f"{note_field}"
        f'<button type="submit" style="display:inline-block;background:{btn_color};color:#fff;border:0;'
        'cursor:pointer;font-weight:600;font-size:14px;padding:12px 22px;border-radius:10px;">'
        f"Verify &amp; {_esc(_DECISION_LABEL[decision])}</button>"
        "</form>"
    )


@router.get("/action", response_class=HTMLResponse)
def action_request_otp(
    decision: str, token: str, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Approver clicked Approve / Request changes in their email. Validate the
    link, email a one-time code, and show the code-entry page. The code's hash is
    carried in a short-lived signed token (no server-side state)."""
    if decision not in _VALID_DECISIONS:
        return _message_page("Unknown action", "This approval link isn't valid.", status_code=400)
    ids = _decode(token)
    if ids is None:
        return _message_page(
            "Link expired", "This approval link is invalid or has expired.", status_code=410
        )
    brief_id, approver_id = ids
    try:
        brief, approver, lane = brief_service.resolve_link_action(db, brief_id, approver_id)
    except brief_service.ApprovalLinkError as e:
        return _message_page("Nothing to do", str(e), status_code=409)
    if not approver.email:
        return _message_page(
            "No email on file",
            "Your account has no email address to send a verification code to.",
            status_code=409,
        )

    otp = approval_links.generate_otp()
    try:
        email_service.send_approval_otp(
            to_addr=approver.email,
            to_name=approver.full_name,
            otp=otp,
            brief_title=brief.project_name or brief.product_name or "Untitled brief",
            decision_label=_DECISION_LABEL[decision],
        )
    except Exception:
        return _message_page(
            "Couldn't send code",
            "We couldn't email your one-time code just now. Please open the link again in a moment.",
            status_code=502,
        )

    # The guess budget for this code lives in the DB, not the token — see
    # ApprovalOtp. `jti` ties the two together.
    jti = uuid.uuid4()
    db.add(
        ApprovalOtp(
            id=jti,
            brief_id=brief_id,
            approver_id=approver_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=_OTP_TTL_SEC),
        )
    )
    db.commit()

    otp_token = approval_links.sign_payload(
        {
            "brief_id": str(brief_id),
            "approver_id": str(approver_id),
            "decision": decision,
            "otp_hash": approval_links.hash_otp(otp),
            "jti": str(jti),
        },
        expires_in_sec=_OTP_TTL_SEC,
    )
    return _page(
        _otp_form_html(
            otp_token,
            decision,
            lane=lane,
            masked_email=approval_links.mask_email(approver.email),
            brief=brief,
        )
    )


@router.post("/action", response_class=HTMLResponse)
def action_submit(
    otp_token: str = Form(...),
    otp: str = Form(...),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Verify the one-time code and record the decision. Re-validates the brief
    server-side (it may have moved on since the code was issued)."""
    try:
        payload = verify_token(otp_token)
    except ValueError:
        return _message_page(
            "Code expired",
            "This code has expired. Open the link in your email again to get a new one.",
            status_code=410,
        )
    decision = payload.get("decision")
    if decision not in _VALID_DECISIONS:
        return _message_page("Unknown action", "This request isn't valid.", status_code=400)

    # The guess budget is held server-side, so replaying an earlier copy of the
    # token can't reset it. No row (or a spent one) means this code is finished.
    record = db.get(ApprovalOtp, uuid.UUID(payload["jti"])) if payload.get("jti") else None
    if record is None or record.consumed:
        return _message_page(
            "Code already used",
            "This code has already been used or is no longer valid. Open the link in "
            "your email again to get a new one.",
            status_code=410,
        )
    if record.attempts >= _MAX_OTP_ATTEMPTS:
        return _message_page(
            "Too many attempts",
            "That code was entered incorrectly too many times. Open the link in your "
            "email again to get a new one.",
            status_code=429,
        )

    if not approval_links.verify_otp(otp or "", payload.get("otp_hash", "")):
        record.attempts += 1
        db.commit()
        left = _MAX_OTP_ATTEMPTS - record.attempts
        if left <= 0:
            return _message_page(
                "Too many attempts",
                "That code was entered incorrectly too many times. Open the link in "
                "your email again to get a new one.",
                status_code=429,
            )
        return _page(
            _otp_form_html(
                otp_token,
                decision,
                error=(
                    "That code doesn't match. "
                    f"{left} attempt{'' if left == 1 else 's'} left before it's blocked."
                ),
            ),
            status_code=401,
        )

    # Correct code — spend it before recording, so it can't be replayed.
    record.consumed = True
    db.commit()

    try:
        brief_id = uuid.UUID(payload["brief_id"])
        approver_id = uuid.UUID(payload["approver_id"])
        brief_service.decide_from_link(db, brief_id, approver_id, decision, note)
    except brief_service.ApprovalLinkError as e:
        return _message_page("Nothing to do", str(e), status_code=409)

    if decision == "approve":
        return _message_page(
            "Approved", "Your approval has been recorded. Thank you — the team has been notified."
        )
    return _message_page(
        "Changes requested",
        "Your feedback has been recorded and sent back to the team. Thank you.",
    )
