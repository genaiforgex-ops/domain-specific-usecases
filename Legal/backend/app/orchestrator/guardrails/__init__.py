"""Safety layer for the orchestrator: PII masking and input/output armor.

Two independent concerns:
  - `pii`: reversible masking of sensitive identifiers before the text ever
    reaches the model, and restoration on the way out.
  - `armor`: input screening (prompt-injection / jailbreak / out-of-scope) and
    output sanitization (internal agent/tool-name stripping).

The default implementations run locally (regex + heuristics) so no legal data
leaves JFPSL infra. A `orch_dlp_enabled` seam is left for dropping in Google
Cloud DLP + Model Armor later without changing call sites.
"""

from app.orchestrator.guardrails.armor import (
    ArmorVerdict,
    sanitize_output,
    screen_input,
)
from app.orchestrator.guardrails.pii import mask_pii, restore_pii

__all__ = [
    "ArmorVerdict",
    "mask_pii",
    "restore_pii",
    "sanitize_output",
    "screen_input",
]
