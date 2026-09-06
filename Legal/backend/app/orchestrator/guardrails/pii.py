"""Reversible PII masking for legal chat.

Sensitive identifiers are replaced with stable placeholders (``PAN_1``,
``AADHAAR_1`` …) BEFORE the text reaches the model, and restored afterwards
using the returned ``pii_map``. This keeps raw identifiers out of the model
call, out of session state, and out of any external model provider.

Detection is local regex by default (no data leaves the process). The pattern
set is tuned for Indian legal / BFSI documents. A Google Cloud DLP path can be
added behind ``settings.orch_dlp_enabled`` without changing callers.

The ``pii_map`` stored in session state is placeholder→original, so a later
turn can still restore placeholders that appeared in earlier context.
"""

from __future__ import annotations

import re
from typing import Pattern

# Order matters: match the most specific / structured identifiers first so a
# PAN is not partially swallowed by a looser alphanumeric rule.
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # Indian PAN: 5 letters, 4 digits, 1 letter.
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    # Aadhaar: 12 digits, optionally space/hyphen grouped 4-4-4.
    ("AADHAAR", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")),
    # GSTIN: 15 chars (state code + PAN + entity + Z + checksum).
    ("GSTIN", re.compile(r"\b\d{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")),
    # IFSC: 4 letters, 0, 6 alphanumerics.
    ("IFSC", re.compile(r"\b[A-Z]{4}0[0-9A-Z]{6}\b")),
    # Credit / debit card: 13-16 digits, optional separators.
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    # Email.
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # Indian phone: optional +91 / 0, then a 10-digit number starting 6-9,
    # allowing one space/hyphen inside the number (e.g. "98765 43210").
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    # Bank account: 9-18 digit run (checked after card/phone/aadhaar).
    ("ACCOUNT", re.compile(r"(?<!\d)\d{9,18}(?!\d)")),
]


def mask_pii(text: str) -> tuple[str, dict[str, str]]:
    """Return ``(masked_text, pii_map)`` where ``pii_map`` is placeholder→original.

    Identical original values reuse the same placeholder, so ``foo@bar.com``
    mentioned twice becomes ``EMAIL_1`` both times.
    """
    if not text:
        return text, {}

    pii_map: dict[str, str] = {}
    original_to_placeholder: dict[str, str] = {}
    counters: dict[str, int] = {}
    masked = text

    for label, pattern in _PATTERNS:

        def _replace(match: re.Match[str]) -> str:
            original = match.group(0)
            if original in original_to_placeholder:
                return original_to_placeholder[original]
            counters[label] = counters.get(label, 0) + 1
            placeholder = f"{label}_{counters[label]}"
            original_to_placeholder[original] = placeholder
            pii_map[placeholder] = original
            return placeholder

        masked = pattern.sub(_replace, masked)

    return masked, pii_map


def restore_pii(text: str, pii_map: dict[str, str]) -> str:
    """Swap placeholders back to their original values.

    Longest placeholders first so ``EMAIL_10`` is restored before ``EMAIL_1``.
    """
    if not text or not pii_map:
        return text
    restored = text
    for placeholder in sorted(pii_map, key=len, reverse=True):
        restored = restored.replace(placeholder, pii_map[placeholder])
    return restored
