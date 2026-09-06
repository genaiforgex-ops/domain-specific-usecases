"""Prompt Studio — a user's override of the shared hero-image "design prompt" base.

One value per user (unlike image_prompt_service, which is per template). The default
base lives in banner_image_service (`default_design_base`); this service only stores
and resolves the override. `get_active_prompt` is the hot path the image generator
calls; `get_state`/`set_prompt`/`reset` back the Prompt Studio editor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.design_prompt import DesignPrompt


@dataclass(frozen=True)
class DesignPromptState:
    """The design base as the user sees it: the built-in default and their override."""

    default_prompt: str
    override: DesignPrompt | None

    @property
    def is_custom(self) -> bool:
        return self.override is not None

    @property
    def enabled(self) -> bool:
        return self.override.enabled if self.override else False

    @property
    def prompt(self) -> str:
        """What to show in the editor — the override text, or the default to edit."""
        return self.override.prompt if self.override else self.default_prompt


def _get(db: Session, user_id: uuid.UUID) -> DesignPrompt | None:
    return db.get(DesignPrompt, user_id)


def get_state(db: Session, user_id: uuid.UUID, default_prompt: str) -> DesignPromptState:
    return DesignPromptState(default_prompt=default_prompt, override=_get(db, user_id))


def set_prompt(db: Session, user_id: uuid.UUID, prompt: str, enabled: bool) -> DesignPrompt:
    row = _get(db, user_id)
    if row is None:
        row = DesignPrompt(user_id=user_id)
        db.add(row)
    row.prompt = prompt
    row.enabled = enabled
    db.commit()
    db.refresh(row)
    return row


def reset(db: Session, user_id: uuid.UUID) -> None:
    """Drop the user's override so the built-in design base applies again."""
    row = _get(db, user_id)
    if row is not None:
        db.delete(row)
        db.commit()


def get_active_prompt(db: Session, user_id: uuid.UUID) -> str | None:
    """The override text when set + enabled + non-empty, else None (use the default)."""
    row = _get(db, user_id)
    if row is not None and row.enabled and row.prompt.strip():
        return row.prompt
    return None
