"""Brief reference images — the sample copies / examples the Product Lead attaches
to a brief so everyone down the chain can see what it's built against.

Uploads are decoded and re-encoded to PNG (see image_utils.normalize_upload_to_png)
so the author can hand over whatever their OS produced. Bytes live in the row and
are served back through a dedicated content endpoint, exactly like the Designer's
banner images. The images are also fed to the Designer's hero-image generation as
visual references (see banner_image_service.generate_images).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.brief import Brief
from app.models.brief_event import BriefEventKind
from app.models.brief_reference_image import BriefReferenceImage
from app.models.user import User
from app.services.brief_service import _record
from app.services.image_utils import MAX_UPLOAD_BYTES, normalize_upload_to_png

# A brief carries a handful of references, not a gallery — keeps the read view and
# the design feed focused (and the table small). The design pipeline caps how many
# it actually sends to the image model separately (see MAX_DESIGN_REFERENCES).
MAX_REFERENCE_IMAGES = 8

# How many of a brief's references the Designer's generation feeds to the image
# model. Past a handful the model averages looks instead of following them, so the
# newest few win — mirrors banner_image_service.MAX_REFERENCES.
MAX_DESIGN_REFERENCES = 4


def list_(db: Session, brief_id: uuid.UUID) -> list[BriefReferenceImage]:
    """A brief's reference images, oldest first."""
    return list(
        db.scalars(
            select(BriefReferenceImage)
            .where(BriefReferenceImage.brief_id == brief_id)
            .order_by(BriefReferenceImage.created_at)
        )
    )


def get(db: Session, brief_id: uuid.UUID, image_id: uuid.UUID) -> BriefReferenceImage | None:
    img = db.get(BriefReferenceImage, image_id)
    if img is None or img.brief_id != brief_id:
        return None
    return img


def add(
    db: Session,
    brief: Brief,
    data: bytes,
    filename: str,
    caption: str | None,
    actor: User,
) -> BriefReferenceImage:
    """Attach one reference image to the brief. Normalises the upload to PNG and
    enforces the per-brief cap. Raises ValueError on a bad or excess upload."""
    if not data:
        raise ValueError("Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file is too large (max 10 MB)")
    if len(list_(db, brief.id)) >= MAX_REFERENCE_IMAGES:
        raise ValueError(f"A brief can carry at most {MAX_REFERENCE_IMAGES} reference images")

    png = normalize_upload_to_png(data)
    name = (filename or "reference").strip()[:255] or "reference"

    img = BriefReferenceImage(
        brief_id=brief.id,
        filename=name,
        caption=(caption or "").strip() or None,
        mime_type="image/png",
        data=png,
        uploaded_by_id=actor.id,
        uploaded_by_name=actor.full_name,
    )
    db.add(img)
    _record(
        db,
        brief,
        actor,
        BriefEventKind.reference_added,
        f"Added a reference image ({name})",
    )
    db.commit()
    db.refresh(img)
    return img


def delete(db: Session, brief: Brief, image_id: uuid.UUID, actor: User) -> None:
    """Remove one reference image from the brief."""
    img = get(db, brief.id, image_id)
    if img is None:
        raise ValueError("Reference image not found")
    name = img.filename
    db.delete(img)
    _record(
        db,
        brief,
        actor,
        BriefEventKind.reference_removed,
        f"Removed a reference image ({name})",
    )
    db.commit()


def design_references(db: Session, brief_id: uuid.UUID) -> list[tuple[bytes, str]]:
    """The (bytes, mime) reference images to hand the Designer's image model —
    newest first, capped at MAX_DESIGN_REFERENCES. Empty when the brief has none."""
    images = list_(db, brief_id)
    images.reverse()  # newest first — they win when the cap trims the set
    return [(img.data, img.mime_type) for img in images[:MAX_DESIGN_REFERENCES]]
