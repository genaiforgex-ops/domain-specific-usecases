"""Prompt Studio routes — a user's own hero-image art-direction, per banner template.

Every authenticated user manages their OWN overrides (keyed by user + template);
there is no cross-user access. Listing returns one entry per template (the image
use-cases) with the built-in default folded in; PUT saves an override; DELETE
resets a template back to its default.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.image_prompt import (
    DesignPromptOut,
    DesignPromptUpdate,
    ImagePromptOut,
    ImagePromptUpdate,
)
from app.services import banner_image_service, design_prompt_service, image_prompt_service
from app.services.design_prompt_service import DesignPromptState
from app.services.image_prompt_service import EffectivePrompt

router = APIRouter(prefix="/api/image-prompts", tags=["image-prompts"])


def _design_out(s: DesignPromptState) -> DesignPromptOut:
    return DesignPromptOut(
        default_prompt=s.default_prompt,
        prompt=s.prompt,
        is_custom=s.is_custom,
        enabled=s.enabled,
        updated_at=s.override.updated_at if s.override else None,
    )


def _out(e: EffectivePrompt) -> ImagePromptOut:
    return ImagePromptOut(
        template_id=e.template.id,
        template_name=e.template.name,
        size_names=[s.get("name", "") for s in (e.template.sizes or [])],
        default_prompt=e.default_prompt,
        prompt=e.prompt,
        is_custom=e.is_custom,
        enabled=e.enabled,
        image_aspect=e.template.image_aspect or "",
        image_size=e.template.image_size or "",
        updated_at=e.override.updated_at if e.override else None,
    )


@router.get("", response_model=list[ImagePromptOut])
def list_image_prompts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImagePromptOut]:
    """The current user's image art-direction for every banner template."""
    return [_out(e) for e in image_prompt_service.list_effective(db, user.id)]


@router.get("/base", response_model=DesignPromptOut)
def get_design_prompt(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DesignPromptOut:
    """The current user's shared design-prompt base (their override or the default)."""
    state = design_prompt_service.get_state(db, user.id, banner_image_service.default_design_base())
    return _design_out(state)


@router.put("/base", response_model=DesignPromptOut)
def set_design_prompt(
    payload: DesignPromptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DesignPromptOut:
    """Save the current user's design-prompt base override."""
    design_prompt_service.set_prompt(db, user.id, payload.prompt, payload.enabled)
    state = design_prompt_service.get_state(db, user.id, banner_image_service.default_design_base())
    return _design_out(state)


@router.delete("/base", response_model=DesignPromptOut)
def reset_design_prompt(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DesignPromptOut:
    """Reset the design-prompt base back to the built-in default for the current user."""
    design_prompt_service.reset(db, user.id)
    state = design_prompt_service.get_state(db, user.id, banner_image_service.default_design_base())
    return _design_out(state)


@router.put("/{template_id}", response_model=ImagePromptOut)
def set_image_prompt(
    template_id: uuid.UUID,
    payload: ImagePromptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImagePromptOut:
    """Save the current user's art-direction override for a template."""
    try:
        e = image_prompt_service.set_prompt(
            db, user.id, template_id, payload.prompt, payload.enabled
        )
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex)) from ex
    return _out(e)


@router.delete("/{template_id}", response_model=ImagePromptOut)
def reset_image_prompt(
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImagePromptOut:
    """Reset a template back to its built-in default for the current user."""
    try:
        e = image_prompt_service.reset(db, user.id, template_id)
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex)) from ex
    return _out(e)
