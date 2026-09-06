"""HTML + plain-text builders for notification emails.

Each builder returns ``(subject, body_html, body_text)``. HTML is a small,
inline-styled branded shell (email clients ignore external CSS) with an optional
call-to-action button that deep-links into the app via ``frontend_base_url``.
"""

from __future__ import annotations

import html as _html

from app.config import settings

_ACCENT = "#1730c4"


def _url(path: str) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _wrap_html(title: str, body_html: str, cta_url: str | None, cta_label: str | None) -> str:
    cta = ""
    if cta_url and cta_label:
        cta = (
            f'<tr><td style="padding:8px 0 4px;">'
            f'<a href="{_html.escape(cta_url)}" '
            f'style="display:inline-block;background:{_ACCENT};color:#ffffff;'
            f'text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600;'
            f'font-size:14px;">{_html.escape(cta_label)}</a></td></tr>'
        )
    return f"""\
<!doctype html><html><body style="margin:0;background:#f2f2f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f2f7;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid rgba(60,60,67,0.12);">
  <tr><td style="background:{_ACCENT};padding:16px 24px;color:#ffffff;font-weight:700;font-size:16px;">LegalOS</td></tr>
  <tr><td style="padding:24px;">
    <div style="font-size:17px;font-weight:600;color:#1a1a1a;margin-bottom:10px;">{_html.escape(title)}</div>
    <div style="font-size:14px;line-height:1.6;color:#3a3a3c;">{body_html}</div>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:16px;">{cta}</table>
  </td></tr>
  <tr><td style="padding:16px 24px;border-top:1px solid rgba(60,60,67,0.1);color:#8e8e93;font-size:12px;">
    You're receiving this because you use LegalOS at JFPSL. Manage notifications in Settings.
  </td></tr>
</table>
</td></tr></table></body></html>"""


def _p(text: str) -> str:
    return f'<p style="margin:0 0 10px;">{_html.escape(text)}</p>'


# ── builders ─────────────────────────────────────────────────────────────────

def invite(recipient_name: str, inviter_name: str, role_label: str, accept_url: str) -> tuple[str, str, str]:
    subject = "You've been invited to LegalOS"
    greeting = f"Hi {recipient_name}," if recipient_name else "Hello,"
    body = (
        _p(greeting)
        + _p(
            f"{inviter_name} has invited you to join <strong>LegalOS</strong>, JFPSL's legal AI "
            f"platform, as <strong>{_html.escape(role_label)}</strong>."
        )
        + _p("Click the button below to set your password and activate your account.")
        + _p("This invite link expires in 7 days. If you weren't expecting it, you can ignore this email.")
    )
    html = _wrap_html("Welcome to LegalOS", body, accept_url, "Accept invite & set password")
    text = (
        f"{greeting}\n\n{inviter_name} invited you to join LegalOS as {role_label}.\n"
        f"Set your password and activate your account here (link expires in 7 days):\n{accept_url}\n"
    )
    return subject, html, text


def chat_shared(recipient_name: str, owner_name: str, chat_title: str) -> tuple[str, str, str]:
    subject = f"{owner_name} shared a LawGenie chat with you"
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f'{owner_name} shared the chat "{chat_title}" with you. You have read-only access.')
    )
    html = _wrap_html("A chat was shared with you", body, _url("/jiolegal"), "Open LawGenie")
    text = (
        f"Hi {recipient_name},\n\n{owner_name} shared the chat \"{chat_title}\" with you "
        f"(read-only).\n\nOpen LawGenie: {_url('/jiolegal')}"
    )
    return subject, html, text


def msa_shared(recipient_name: str, sharer_name: str, vendor: str, tracker_id: int, access: str) -> tuple[str, str, str]:
    subject = f"{sharer_name} shared an MSA negotiation with you"
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f"{sharer_name} shared the {vendor} contract negotiation with you ({access} access).")
    )
    url = _url(f"/msa/{tracker_id}")
    html = _wrap_html("An MSA was shared with you", body, url, "Open negotiation")
    text = f"Hi {recipient_name},\n\n{sharer_name} shared the {vendor} MSA with you ({access}).\n\n{url}"
    return subject, html, text


def task_assigned(recipient_name: str, assigner_name: str, task_title: str, due: str | None) -> tuple[str, str, str]:
    subject = f"New task assigned: {task_title}"
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f"{assigner_name} assigned you a task: \"{task_title}\".")
        + (_p(f"Due: {due}.") if due else "")
    )
    html = _wrap_html("A task was assigned to you", body, _url("/tasks"), "View tasks")
    text = f"Hi {recipient_name},\n\n{assigner_name} assigned you: \"{task_title}\"." + (
        f" Due: {due}." if due else ""
    ) + f"\n\n{_url('/tasks')}"
    return subject, html, text


def approval_escalation(recipient_name: str, question: str) -> tuple[str, str, str]:
    subject = "A LegalBot query needs review"
    body = (
        _p(f"Hi {recipient_name},")
        + _p("A LegalBot query was escalated and needs a reviewer's attention:")
        + _p(f'"{question}"')
    )
    html = _wrap_html("Review needed", body, _url("/"), "Open LegalOS")
    text = f"Hi {recipient_name},\n\nA LegalBot query was escalated for review:\n\"{question}\"\n\n{_url('/')}"
    return subject, html, text


def approval_resolved(recipient_name: str, question: str) -> tuple[str, str, str]:
    subject = "Your escalated question was answered"
    body = (
        _p(f"Hi {recipient_name},")
        + _p("A reviewer has resolved your escalated LegalBot question:")
        + _p(f'"{question}"')
    )
    html = _wrap_html("Your question was answered", body, _url("/"), "Open LegalOS")
    text = f"Hi {recipient_name},\n\nYour escalated question was resolved:\n\"{question}\"\n\n{_url('/')}"
    return subject, html, text


def msa_vendor_ingested(recipient_name: str, vendor: str, tracker_id: int) -> tuple[str, str, str]:
    subject = f"New vendor document received — {vendor}"
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f"A new document from {vendor} was received and auto-reviewed. Please take a look.")
    )
    url = _url(f"/msa/{tracker_id}")
    html = _wrap_html("Vendor document received", body, url, "Review document")
    text = f"Hi {recipient_name},\n\nNew document from {vendor} received and auto-reviewed.\n\n{url}"
    return subject, html, text


def regulatory_alert(recipient_name: str, items: list[tuple[str, str]]) -> tuple[str, str, str]:
    """items: list of (regulator, title). Digest of new action-required updates."""
    n = len(items)
    subject = f"{n} new regulatory update{'s' if n != 1 else ''} need review"
    rows = "".join(
        f'<li style="margin:0 0 6px;"><strong>{_html.escape(reg)}:</strong> {_html.escape(title)}</li>'
        for reg, title in items[:10]
    )
    more = f"<p>…and {n - 10} more.</p>" if n > 10 else ""
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f"{n} new regulatory update{'s' if n != 1 else ''} were flagged as action-required:")
        + f'<ul style="margin:0 0 10px;padding-left:18px;">{rows}</ul>'
        + more
    )
    html = _wrap_html("Regulatory updates to review", body, _url("/legal-news"), "Open Legal News")
    text = f"Hi {recipient_name},\n\n{n} new action-required regulatory update(s):\n" + "\n".join(
        f"- {reg}: {title}" for reg, title in items[:10]
    ) + f"\n\n{_url('/legal-news')}"
    return subject, html, text


def msa_executed(recipient_name: str, vendor: str, tracker_id: int) -> tuple[str, str, str]:
    subject = f"MSA executed — {vendor}"
    body = (
        _p(f"Hi {recipient_name},")
        + _p(f"The {vendor} contract has been marked executed (finalized).")
    )
    url = _url(f"/msa/{tracker_id}")
    html = _wrap_html("Contract executed", body, url, "Open negotiation")
    text = f"Hi {recipient_name},\n\nThe {vendor} contract was executed.\n\n{url}"
    return subject, html, text
