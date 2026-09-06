"""Load distilled JFPSL template standards for prompts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_STANDARDS_FILE = Path(__file__).resolve().parent / "jfpsl_template_standards.md"
_MAX_CHARS = 8000


@lru_cache(maxsize=1)
def load_jfpsl_template_standards(*, max_chars: int = _MAX_CHARS) -> str:
    """Return distilled template standards markdown (truncated for token budget)."""
    if not _STANDARDS_FILE.is_file():
        return (
            "(JFPSL template standards file not found under "
            "orchestrator/prompts/. Run "
            "backend/scripts/distill_template_playbook.py to generate it.)"
        )
    text = _STANDARDS_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return "(JFPSL template standards file is empty.)"
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n\n… [truncated]"


def standards_file_path() -> Path:
    return _STANDARDS_FILE
