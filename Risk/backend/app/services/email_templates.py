"""Bodies for the form-flow emails.

Deliberately plain f-strings rather than a template engine: there are two
messages here and the repo carries no templating dependency.

Email-client constraints shape the markup — tables for layout, every style
inlined, no CSS variables and no <style> block, because Gmail strips or ignores
all three. Each builder returns (subject, text, html); the text part is not
decoration, it is the fallback part of the multipart/alternative.
"""

from datetime import datetime

# Hard-coded from the frontend palette in frontend/src/styles/global.css
# (--color-primary / --navy-950 / --color-ink). Mail cannot read CSS variables,
# so these are copies and will need a nudge if the theme changes.
_PRIMARY = "#336699"
_NAVY = "#1a334d"
_INK = "#333333"
_MUTED = "#6b7280"
_BORDER = "#cccccc"


def _fmt_due(due_at: datetime | None) -> str | None:
    if not due_at:
        return None
    return due_at.strftime("%d %b %Y")


def _shell(*, heading: str, intro: str, rows: list[tuple[str, str]], cta_label: str, cta_url: str, footer: str) -> str:
    """One-column card. `rows` renders as a label/value detail table."""
    detail_rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 16px 4px 0;color:{_MUTED};font-size:13px;white-space:nowrap;">{label}</td>'
        f'<td style="padding:4px 0;color:{_INK};font-size:13px;font-weight:600;">{value}</td>'
        f'</tr>'
        for label, value in rows
    )
    # A bare URL under the button: some clients strip or mangle the anchor, and a
    # form invite with no reachable link is worthless.
    return f"""\
<div style="margin:0;padding:24px 12px;background-color:#f2f6fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:560px;margin:0 auto;background-color:#ffffff;border:1px solid {_BORDER};border-radius:8px;">
    <tr>
      <td style="padding:20px 28px;background-color:{_NAVY};border-radius:8px 8px 0 0;">
        <div style="color:#ffffff;font-size:15px;font-weight:700;letter-spacing:0.3px;">GenAIForge Risk</div>
      </td>
    </tr>
    <tr>
      <td style="padding:28px;">
        <h1 style="margin:0 0 12px;color:{_INK};font-size:19px;font-weight:700;">{heading}</h1>
        <p style="margin:0 0 20px;color:{_INK};font-size:14px;line-height:1.55;">{intro}</p>
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px;">
          {detail_rows}
        </table>
        <a href="{cta_url}" style="display:inline-block;padding:11px 22px;background-color:{_PRIMARY};color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;border-radius:6px;">{cta_label}</a>
        <p style="margin:20px 0 0;color:{_MUTED};font-size:12px;line-height:1.5;">
          If the button does not work, paste this into your browser:<br>
          <span style="color:{_PRIMARY};word-break:break-all;">{cta_url}</span>
        </p>
      </td>
    </tr>
    <tr>
      <td style="padding:16px 28px;border-top:1px solid {_BORDER};color:{_MUTED};font-size:12px;line-height:1.5;">
        {footer}
      </td>
    </tr>
  </table>
</div>"""


def form_assigned(*, title: str, vendor_name: str, due_at: datetime | None, url: str) -> tuple[str, str, str]:
    due = _fmt_due(due_at)
    subject = f"[GenAIForge Risk] Form assigned: {title}"

    text_lines = [
        f'You have been assigned the form "{title}".',
        "",
        f"Vendor: {vendor_name}",
    ]
    if due:
        text_lines.append(f"Due: {due}")
    text_lines += ["", "Open it here:", url, "", "— GenAIForge Risk"]

    rows = [("Form", title), ("Vendor", vendor_name)]
    if due:
        rows.append(("Due", due))

    html = _shell(
        heading="A form has been assigned to you",
        intro=(
            "You have been assigned a vendor due-diligence form to complete. "
            + (f"Please submit it by <strong>{due}</strong>." if due else "Please complete it at your earliest convenience.")
        ),
        rows=rows,
        cta_label="Open the form",
        cta_url=url,
        footer="You are receiving this because the form was assigned to your GenAIForge Risk account. Administrators are copied on this message.",
    )
    return subject, "\n".join(text_lines), html


def form_reminder(*, title: str, vendor_name: str, due_at: datetime | None, url: str) -> tuple[str, str, str]:
    due = _fmt_due(due_at)
    subject = f"[GenAIForge Risk] Reminder: {title}"

    text_lines = [
        f'This is a reminder to complete the form "{title}".',
        "",
        f"Vendor: {vendor_name}",
    ]
    if due:
        text_lines.append(f"Due: {due}")
    text_lines += ["", "Open it here:", url, "", "— GenAIForge Risk"]

    rows = [("Form", title), ("Vendor", vendor_name)]
    if due:
        rows.append(("Due", due))

    html = _shell(
        heading="Reminder: your form is still open",
        intro=(
            "This form is assigned to you and has not been submitted yet. "
            + (f"It is due on <strong>{due}</strong>." if due else "Please complete it when you can.")
        ),
        rows=rows,
        cta_label="Complete the form",
        cta_url=url,
        footer="You are receiving this because the form is still open against your GenAIForge Risk account. Administrators are copied on this message.",
    )
    return subject, "\n".join(text_lines), html
