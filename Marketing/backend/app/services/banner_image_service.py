"""Banner hero imagery — Nano Banana (Gemini image model) generation + review.

Once a brief reaches the Designer (stage = design), the Designer generates a hero
image for each creative with Nano Banana, reviews them, regenerates any that miss,
and approves the set. Approved images are what the Figma export uploads and fills
the banners with. The image is purely the *hero photo*: the banner template lays
the headline, body, CTA and footer over the brand frame, so the prompt asks for a
clean, text-free composition with room around the subject.
"""

import uuid

import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.banner_image import BannerImage, BannerImageStatus
from app.models.banner_image_message import BannerImageMessage
from app.models.brief import Brief, BriefStage
from app.models.brief_event import BriefEventKind
from app.models.creative import Creative
from app.models.user import User
from app.services import ai_log_service, brief_reference_service
from app.services.brief_service import _record
from app.services.image_utils import (
    ALLOWED_UPLOAD_TYPES as _ALLOWED_UPLOAD_TYPES,
    MAX_UPLOAD_BYTES,
    normalize_upload_to_png as _normalize_upload_to_png,
)

logger = logging.getLogger("uvicorn.error")

# Brand art-direction baked into every hero prompt. GenAIForge hero imagery is
# people-first lifestyle photography — NOT product shots. (The ink + bronze frame
# is the graphic chrome the banner adds around the photo, never the photo itself.)
_BRAND_PHOTOGRAPHY = (
    "GenAIForge brand photography. Real, warm and human lifestyle photography — "
    "never staged or artificial. People first, technology second. Always optimistic.\n"
    "- People & moments: real people in everyday life (home, work, learning, "
    "play); natural expressions, genuine emotion, moments of connection and ease; any "
    "phone or device sits quietly within the scene, never the hero.\n"
    "- Light & colour: soft, natural light; warm, balanced tones; vibrant but "
    "true-to-life colour and authentic skin tones.\n"
    "- Composition & finish: simple, uncluttered framing at human eye level; a medium "
    "shot, close-up or environmental portrait; subtle grading, premium yet restrained; "
    "shot on a full-frame camera with a fast prime lens, natural depth of field and real "
    "skin texture."
)

# Hard constraints. The banner overlays its own copy, logo and dot ribbon, so the
# photo must stay text-free with calm space for the overlay — and, per the playbook,
# must read as a genuine photograph, never as an AI render or illustration. The
# COMPOSITION (where the subject sits / where negative space is left) is supplied
# per banner template — see _DEFAULT_COMPOSITION and each template's image_brief.
_CONSTRAINTS_BASE = (
    "It must look like a real editorial photograph — NOT AI-generated, NOT 3D, NOT an "
    "illustration. No text, words, letters, numbers, logos, watermarks, app UI or graphic "
    "overlays anywhere in the image. The photograph must be full-bleed and edge-to-edge: "
    "absolutely NO border, frame, outline, margin, padding, passe-partout, matte, vignette, "
    "rounded corners or coloured bars on any side — the image content must fill the entire "
    "frame right to every edge. Warm, true-to-life tones."
)

# Composition used when no template art-direction is supplied (mirrors the
# performance-ad brief, so behaviour is unchanged when a template isn't specified).
_DEFAULT_COMPOSITION = (
    "Place the subject slightly off-centre and keep calm, uncluttered negative space "
    "to one side so a headline and logo can be added later. Frame so it crops cleanly "
    "to both tall (story/portrait) and wide (landscape) formats."
)

# Quality bar — GenAIForge hero imagery must read as premium, high-end advertising
# photography. These directives push the image model toward maximum fidelity.
_QUALITY = (
    "Render at the highest possible quality: ultra-high resolution, crisp and "
    "tack-sharp focus on the subject, fine real skin texture and pore-level detail, "
    "rich dynamic range, true-to-life colour depth and a clean, noise-free image with "
    "only a subtle natural film grain. Shot on a full-frame camera with a fast prime "
    "lens, natural shallow depth of field and soft bokeh, professional studio-grade "
    "colour grading. Award-winning commercial advertising photography, magazine-cover "
    "quality, photorealistic."
)


# The editable "design prompt" base shared by every hero image — brand photography
# rules, the text-free/full-bleed constraints and the quality bar. The per-creative
# scene and the per-format composition are appended by _image_prompt (they stay
# system-owned), so a Designer can rewrite this base without breaking those wirings.
_DEFAULT_DESIGN_BASE = f"{_BRAND_PHOTOGRAPHY}\n\n{_CONSTRAINTS_BASE}\n\n{_QUALITY}"


def default_design_base() -> str:
    """The built-in design-prompt base (the reset target / starting point to edit)."""
    return _DEFAULT_DESIGN_BASE


def _image_prompt(
    creative: Creative, composition: str | None = None, design_base: str | None = None
) -> str:
    """Assemble a hero-image prompt: the design base (editable, brand scaffold by
    default) + the creative's scene + this format's composition.

    `composition` is the chosen banner template's art-direction (where the subject
    sits / which side to leave clear for copy); `design_base` is the user's Design
    prompt override (defaults to the brand scaffold). Both default so generation
    without a template or override is unchanged."""
    subject = (creative.visual_reference or "").strip()
    if not subject:
        # No art note: build a verbose, people-first scene from the copy, per brand
        # (people first, technology second) rather than a product/gold still life.
        subject = (
            "An optimistic, everyday Indian family in their early thirties at home in "
            "soft natural daylight — a parent and young child sharing a warm, relaxed "
            "moment on the sofa, a smartphone resting naturally nearby but not the "
            "focus, dressed in warm everyday colours, eye-level medium shot with calm "
            "negative space, genuine smiles and a feeling of ease and quiet confidence "
            f"about their financial future — evoking the message: {creative.headline.strip()}."
        )
    base = (design_base or "").strip() or _DEFAULT_DESIGN_BASE
    return (
        f"{base}\n\n"
        f"Scene to photograph: {subject}\n\n"
        f"Composition for this format: {composition or _DEFAULT_COMPOSITION}"
    )


def _resolve_design_base(db: Session, user_id: uuid.UUID) -> str:
    """The Design prompt to generate with: the user's enabled override, else the
    built-in brand scaffold."""
    from app.services import design_prompt_service

    return design_prompt_service.get_active_prompt(db, user_id) or _DEFAULT_DESIGN_BASE


def _call_image_model(contents, config) -> tuple[bytes, str, dict, int]:
    """One Nano Banana call. Returns (image bytes, mime type, usage, latency)."""
    from google import genai  # local import — keeps the SDK off the import path until used

    client = genai.Client(api_key=settings.gemini_api_key)
    started = time.perf_counter()
    resp = client.models.generate_content(
        model=settings.image_model, contents=contents, config=config
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    um = getattr(resp, "usage_metadata", None)
    usage = {
        "input_tokens": int(getattr(um, "prompt_token_count", 0) or 0),
        "output_tokens": int(getattr(um, "candidates_token_count", 0) or 0),
    }
    for part in resp.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            # Trust the model's own mime type — it is not always PNG, and storing a
            # JPEG mislabelled as PNG breaks the Figma upload and the download name.
            return inline.data, _image_mime(getattr(inline, "mime_type", "")), usage, latency_ms
    raise RuntimeError("Nano Banana returned no image for the prompt")


def _image_mime(reported: str) -> str:
    """The model's mime type, sanitised for the (64-char) column — PNG if unusable."""
    mime = (reported or "").split(";")[0].strip().lower()
    return mime if mime.startswith("image/") and len(mime) <= 64 else "image/png"


def _run_image_model(contents, config=None) -> tuple[bytes, str, dict, int]:
    """Call Nano Banana, degrading the image config if the field isn't supported here.

    An image_config field can be refused two ways: the API answers 400, or the SDK
    itself raises a ValueError before sending, because several fields only exist in
    Vertex/Enterprise mode and we call the Developer API with an API key. Either way,
    fall back to aspect-only and then to the model's defaults rather than failing the
    Designer's generate or edit.
    """
    from google.genai import errors

    last: Exception | None = None
    for attempt in _config_ladder(config):
        try:
            return _call_image_model(contents, attempt)
        except (errors.ClientError, ValueError) as exc:
            # Only a complaint about the config itself is worth another call — a 400
            # about the prompt would just fail again at the caller's expense.
            http_400 = not isinstance(exc, errors.ClientError) or exc.code == 400
            if not http_400 or not _is_config_rejection(exc):
                raise
            logger.warning("Nano Banana rejected the image config (%s) — retrying simpler", exc)
            last = exc
    raise last or RuntimeError("Nano Banana returned no image for the prompt")


# Both spellings: the SDK sends snake_case, the API echoes unknown names in camelCase.
_CONFIG_FIELDS = (
    "image_config",
    "imageConfig",
    "image_size",
    "imageSize",
    "output_mime_type",
    "outputMimeType",
    "aspect_ratio",
    "aspectRatio",
)


def _is_config_rejection(exc: Exception) -> bool:
    """Whether the refusal names an image_config field unsupported in this mode."""
    message = str(exc)
    return any(field in message for field in _CONFIG_FIELDS)


def _config_ladder(config) -> list:
    """`config` followed by progressively simpler variants to retry a 400 with."""
    from google.genai import types

    image_config = getattr(config, "image_config", None) if config else None
    if image_config is None:
        return [config]
    ladder = [config]
    if image_config.aspect_ratio:  # keep the format's shape, drop the rest
        ladder.append(
            types.GenerateContentConfig(
                image_config=types.ImageConfig(aspect_ratio=image_config.aspect_ratio)
            )
        )
    ladder.append(None)  # last resort: the model's own defaults
    return ladder


def _hero_image_config(aspect: str = "", size: str = ""):
    """A GenerateContentConfig pinning a hero photo's output shape and resolution
    (real image-model params, not prompt text).

    `aspect` empty means "keep the input's aspect ratio", which is what an edit wants
    — the Designer may have cropped the photo by hand since it was generated. `size`
    empty falls back to the configured tier (settings.image_size), because the model's
    own default is ~1K and every edit re-renders from it.

    Aspect and size are the only two image_config fields the Developer API accepts:
    output_mime_type and friends are Vertex/Enterprise-only and the SDK raises before
    it sends. The model returns PNG by default anyway, and _call_image_model records
    whatever mime type actually comes back.
    """
    from google.genai import types

    return types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio=aspect or None,
            image_size=size or settings.image_size or None,
        )
    )


# The shapes the image model will answer in, widest first.
_ASPECTS: tuple[tuple[str, float], ...] = (
    ("21:9", 21 / 9),
    ("16:9", 16 / 9),
    ("3:2", 3 / 2),
    ("4:3", 4 / 3),
    ("5:4", 5 / 4),
    ("1:1", 1.0),
    ("4:5", 4 / 5),
    ("3:4", 3 / 4),
    ("2:3", 2 / 3),
    ("9:16", 9 / 16),
)


def _source_aspect(data: bytes) -> str:
    """The supported aspect ratio nearest this image's own shape ("" if unreadable).

    An edit has to ask for its shape rather than assume it is kept. Left to choose, the
    model answers in the aspect of whichever input it finds most salient, and as soon as
    the Designer attaches a portrait headshot to a 16:9 hero that input is the reference:
    the reply comes back portrait and _conform_to_source crops a landscape band out of
    the middle, taking the subject's head off. Naming the base's own ratio keeps it.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            ratio = im.width / im.height
    except Exception:  # noqa: BLE001 — an unreadable base just means "no preference"
        logger.exception("Could not read the base image's aspect ratio")
        return ""
    return min(_ASPECTS, key=lambda pair: abs(pair[1] - ratio))[0]


def _template_image_size(db: Session, template_id: uuid.UUID | None) -> str:
    """The output resolution tier the chosen template pins ("" = use the default)."""
    from app.services import banner_template_service

    _row, bundle = banner_template_service.resolve_bundle(db, template_id)
    return (bundle.image_size or "").strip()


def _image_gen_config(db: Session, template_id: uuid.UUID | None):
    """Generation config for the chosen template — its aspect ratio (so the hero's
    shape matches the format, e.g. messaging → 16:9) at its resolution tier."""
    from app.services import banner_template_service

    _row, bundle = banner_template_service.resolve_bundle(db, template_id)
    return _hero_image_config(
        aspect=(bundle.image_aspect or "").strip(), size=(bundle.image_size or "").strip()
    )


# Framing for the brief's reference images when they ride along with a fresh
# generation. They are the Product Lead's samples/examples, so they steer the look
# — but the hero must still be a clean, text-free photograph per the constraints.
_REFERENCE_FRAMING = (
    "\n\nReference images from the brief follow this instruction. Treat them as "
    "visual direction only — take cues from their subject, styling, mood, colour "
    "and composition where they suit the brief. Do NOT reproduce any text, logos, "
    "watermarks, app UI or graphics from them, and still honour every constraint "
    "above (a real, text-free editorial photograph with room for the overlay)."
)


def _generate_png(
    prompt: str, config=None, references: list[tuple[bytes, str]] | None = None
) -> tuple[bytes, str, dict, int]:
    """Generate a fresh hero image from a text prompt, optionally guided by the
    brief's reference images. Returns (png, mime, usage, latency)."""
    refs = references or []
    if not refs:
        return _run_image_model(prompt, config)

    from google.genai import types

    contents = [prompt + _REFERENCE_FRAMING]
    contents.extend(types.Part.from_bytes(data=data, mime_type=mime) for data, mime in refs)
    return _run_image_model(contents, config)


def _edit_png(
    prompt: str,
    base_png: bytes,
    mime_type: str,
    config=None,
    references: list[tuple[bytes, str]] | None = None,
) -> tuple[bytes, str, dict, int]:
    """Edit an existing image: pass the current PNG plus the instruction to Nano Banana.

    `config` carries the resolution tier — without it the edit comes back at the
    model's default ~1K, which is a downscale of anything generated larger.

    The photo being edited goes first and the Designer's reference images follow it.
    """
    from google.genai import types

    contents = [prompt, types.Part.from_bytes(data=base_png, mime_type=mime_type)]
    contents.extend(
        types.Part.from_bytes(data=data, mime_type=mime) for data, mime in references or []
    )
    return _run_image_model(contents, config)


def _conform_to_source(data: bytes, mime_type: str, source: bytes) -> tuple[bytes, str]:
    """Pin an edited image back to the exact pixel dimensions it was handed, losslessly.

    Nothing in the prompt guards this any more, and prose never did it reliably anyway:
    image_config pins a size *tier* ("2K"), the model answers in one of its own buckets,
    and if the config is refused _config_ladder quietly drops to the model's ~1K default.
    Whatever comes back is stored and becomes the base for the next turn, so three things
    compound with every pass — the frame drifts a little, it can shrink a lot after a
    config rejection, and a JPEG answer is recompressed again. Five edits in, the photo
    is visibly smaller and softer than after one.

    Conforming each result to its source stops all three: dimensions are inherited
    from the base version forever, and the stored bytes are always lossless.

    Falls back to the model's own bytes if the image can't be read — a stored edit is
    worth more than a failed one.
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(source)) as src:
            target = src.size
        with Image.open(io.BytesIO(data)) as out:
            if out.size == target and mime_type == "image/png":
                return data, mime_type  # already exact and lossless — leave it alone
            # fit() scales to cover and crops, so an answer that came back in a different
            # aspect bucket is trimmed rather than stretched out of shape. The crop sits
            # above centre because these are photographs of people: when a taller frame
            # has to lose height, the half worth keeping is the one with the faces in it.
            fitted = ImageOps.fit(
                out.convert("RGB"), target, method=Image.LANCZOS, centering=(0.5, 0.25)
            )
        buf = io.BytesIO()
        fitted.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    except Exception:  # noqa: BLE001 — never lose a completed edit to a decode problem
        logger.exception("Could not conform an edited image to its source dimensions")
        return data, mime_type


def _upsert_image(
    db: Session, creative: Creative, png: bytes, mime_type: str, prompt: str
) -> BannerImage:
    """Create or replace the creative's hero image, resetting it to 'pending'.

    (Re)generating from scratch resets the Designer's chat thread to a single base
    version, since any prior conversation was about the image we just replaced.
    """
    img = creative.banner_image
    if img is None:
        img = BannerImage(creative_id=creative.id, brief_id=creative.brief_id)
        db.add(img)
    img.prompt = prompt
    img.data = png
    img.mime_type = mime_type
    img.status = BannerImageStatus.pending.value
    img.model_version = settings.image_model
    img.messages.clear()  # drop the old thread…
    seed = BannerImageMessage(  # …and seed it with this base version (no comment)
        comment=None,
        prompt=prompt,
        data=png,
        mime_type=mime_type,
        model_version=settings.image_model,
    )
    img.messages.append(seed)
    img.active_message = seed  # the base version is the live one until edited
    return img


def _resolve_composition(
    db: Session, user_id: uuid.UUID, template_id: uuid.UUID | None
) -> str:
    """The hero-photo art-direction to generate with: the user's Prompt Studio
    override for the chosen template when set+enabled, else the template's built-in
    brief, else the default composition. Raises ValueError if a specific template_id
    is given but does not exist."""
    from app.services import banner_template_service, image_prompt_service

    row, bundle = banner_template_service.resolve_bundle(db, template_id)
    default = bundle.image_brief or _DEFAULT_COMPOSITION
    return image_prompt_service.resolve_brief(db, user_id, row, default)


def select_template(
    db: Session, brief: Brief, template_id: uuid.UUID, actor: User
) -> Brief:
    """Persist the Designer's banner-template pick for this brief.

    The pick is made *before* the hero images are generated, because the template
    art-directs the photograph (where the subject sits, what shape it is) as well as
    rendering the export. Storing it on the brief keeps generation, regeneration and
    the Figma export on the same template across reloads. The choice is confined to
    the category the Product Lead locked on the brief.
    """
    from app.services import banner_template_service

    tpl = banner_template_service.get(db, template_id)
    if tpl is None:
        raise ValueError("Banner template not found")
    if brief.banner_category and tpl.category != brief.banner_category:
        raise ValueError("That template is outside the banner category set on this brief")
    if brief.banner_template_id == tpl.id:
        return brief  # idempotent — re-picking the same template is not an event

    brief.banner_template_id = tpl.id
    _record(
        db,
        brief,
        actor,
        BriefEventKind.banner_template_selected,
        f"Selected the '{tpl.name}' banner template",
    )
    db.commit()
    db.refresh(brief)
    return brief


def require_template_id(
    db: Session, brief: Brief, requested: uuid.UUID | None = None
) -> uuid.UUID | None:
    """The template to compose hero images for: the one named in the request, else
    the one the Designer picked on the brief.

    Raises ValueError when neither is set but the brief's category *has* templates
    to choose from — the composition is template-specific, so generating before the
    Designer has picked would silently art-direct the photos for the wrong layout.
    """
    from app.services import banner_template_service

    chosen = requested or brief.banner_template_id
    if chosen is None and banner_template_service.list_templates(db, brief.banner_category):
        raise ValueError("Pick a banner template before generating hero images")
    return chosen


def generate_images(
    db: Session, brief: Brief, actor: User, template_id: uuid.UUID | None = None
) -> list[BannerImage]:
    """Generate a hero image for every creative on the brief (concurrently),
    composed for the chosen banner template (default template when None)."""
    creatives = list(brief.creatives)
    if not creatives:
        return []

    composition = _resolve_composition(db, actor.id, template_id)
    design_base = _resolve_design_base(db, actor.id)
    gen_config = _image_gen_config(db, template_id)
    prompts = {c.id: _image_prompt(c, composition, design_base) for c in creatives}
    # The Product Lead's sample/example images on the brief steer the look.
    references = brief_reference_service.design_references(db, brief.id)

    # Nano Banana calls are independent and I/O-bound — fan them out, but bound
    # the concurrency so a large set doesn't hammer the API.
    def _work(cid_prompt: tuple[int, str]) -> tuple[int, tuple[bytes, str, dict, int] | None]:
        cid, prompt = cid_prompt
        try:
            return cid, _generate_png(prompt, gen_config, references)
        except Exception:  # noqa: BLE001 — one failed image shouldn't sink the batch
            logger.exception("Nano Banana failed for creative %d", cid)
            return cid, None

    with ThreadPoolExecutor(max_workers=min(4, len(creatives))) as pool:
        results = dict(pool.map(_work, prompts.items()))

    saved: list[BannerImage] = []
    traces: list[tuple[int, dict, int]] = []
    for c in creatives:
        result = results.get(c.id)
        if result:
            png, mime_type, usage, latency_ms = result
            saved.append(_upsert_image(db, c, png, mime_type, prompts[c.id]))
            traces.append((c.id, usage, latency_ms))

    if not saved:
        raise RuntimeError("Image generation failed for every creative")

    _record(
        db,
        brief,
        actor,
        BriefEventKind.banner_images_generated,
        f"Generated {len(saved)} banner image{'s' if len(saved) != 1 else ''} "
        f"({settings.image_model})",
    )
    for cid, usage, latency_ms in traces:
        ai_log_service.record_call(
            db,
            operation="banner_image",
            model=settings.image_model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            latency_ms=latency_ms,
            brief_id=brief.id,
            creative_id=cid,
            actor_id=actor.id,
            commit=False,
        )
    db.commit()
    for img in saved:
        db.refresh(img)
    return saved


def regenerate_image(
    db: Session,
    brief: Brief,
    creative_id: uuid.UUID,
    actor: User,
    template_id: uuid.UUID | None = None,
) -> BannerImage:
    """Regenerate a single creative's hero image (back to 'pending'), composed for
    the chosen banner template (default template when None)."""
    creative = next((c for c in brief.creatives if c.id == creative_id), None)
    if creative is None:
        raise ValueError("creative not found on this brief")
    prompt = _image_prompt(
        creative,
        _resolve_composition(db, actor.id, template_id),
        _resolve_design_base(db, actor.id),
    )
    references = brief_reference_service.design_references(db, brief.id)
    png, mime_type, usage, latency_ms = _generate_png(
        prompt, _image_gen_config(db, template_id), references
    )
    img = _upsert_image(db, creative, png, mime_type, prompt)
    ai_log_service.record_call(
        db,
        operation="banner_image",
        model=settings.image_model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        latency_ms=latency_ms,
        brief_id=brief.id,
        creative_id=creative.id,
        actor_id=actor.id,
        commit=False,
    )
    db.commit()
    db.refresh(img)
    return img


# Reference images ride along with a single chat turn. The cap bounds one request:
# they're sent to the model on top of the photo being edited, and past a handful the
# model starts averaging looks instead of following one.
MAX_REFERENCES = 4


def validate_references(references: list[tuple[bytes, str]]) -> None:
    """Check the reference images attached to a chat turn. Raises ValueError."""
    if len(references) > MAX_REFERENCES:
        raise ValueError(f"Attach at most {MAX_REFERENCES} reference images")
    for data, mime_type in references:
        if mime_type not in _ALLOWED_UPLOAD_TYPES:
            raise ValueError("Unsupported reference image type — use PNG, JPEG or WEBP")
        if not data:
            raise ValueError("A reference image is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("A reference image is too large (max 10 MB)")


def upload_image(
    db: Session,
    brief: Brief,
    image_id: uuid.UUID,
    data: bytes,
    mime_type: str,
    actor: User,
) -> BannerImage:
    """Swap in a Designer-supplied photo — the escape hatch when Nano Banana's
    output isn't right. Lands as a new chat-thread version, same as a regenerate
    or an AI edit, so it's still reviewable and revertible before Figma export.

    The upload is decoded and re-encoded to PNG (see _normalize_upload_to_png),
    so the Designer can hand over whatever their OS produced rather than only the
    three exact MIME types the browser happens to label correctly."""
    if not data:
        raise ValueError("Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file is too large (max 10 MB)")

    png = _normalize_upload_to_png(data)
    mime_type = "image/png"

    img = get_image(db, brief.id, image_id)
    if img is None:
        raise ValueError("image not found")
    ensure_seed(db, img)  # keep the original as version 1 before this swap

    prompt = "Uploaded by the Designer (custom image, not AI-generated)"
    img.data = png
    img.prompt = prompt
    img.mime_type = mime_type
    img.status = BannerImageStatus.pending.value
    img.model_version = "manual-upload"
    msg = BannerImageMessage(
        comment="Uploaded a custom image",
        prompt=prompt,
        data=png,
        mime_type=mime_type,
        model_version="manual-upload",
    )
    img.messages.append(msg)
    img.active_message = msg

    _record(
        db,
        brief,
        actor,
        BriefEventKind.banner_image_uploaded,
        "Replaced a banner image with a custom upload",
    )
    db.commit()
    db.refresh(img)
    return img


MAX_SUMMARY_CHARS = 400  # a tool list, not prose — keeps the history line readable


def apply_manual_edit(
    db: Session,
    brief: Brief,
    image_id: uuid.UUID,
    data: bytes,
    mime_type: str,
    summary: str,
    actor: User,
) -> tuple[BannerImage, BannerImageMessage]:
    """Store a Design Studio hand-edit (crop / straighten / tune / sharpen …).

    The pixel work happens in the browser — a slider has to repaint at interactive
    speed — so the Designer posts the flattened result plus a summary of the tools
    they used. It lands as a new version in the same thread as AI edits and custom
    uploads, so the earlier version stays selectable, the Figma export picks the new
    bytes up automatically, and the set drops back to 'pending' for re-approval.
    """
    if mime_type not in _ALLOWED_UPLOAD_TYPES:
        raise ValueError("Unsupported image type — use PNG, JPEG or WEBP")
    if not data:
        raise ValueError("Edited image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Edited image is too large (max 10 MB)")

    img = get_image(db, brief.id, image_id)
    if img is None:
        raise ValueError("image not found")
    ensure_seed(db, img)  # keep the pre-edit version selectable

    summary = (summary or "").strip()[:MAX_SUMMARY_CHARS] or "Manual edit"
    img.data = data
    img.prompt = summary
    img.mime_type = mime_type
    img.status = BannerImageStatus.pending.value
    img.model_version = "manual-edit"
    msg = BannerImageMessage(
        comment=summary,
        prompt=summary,
        data=data,
        mime_type=mime_type,
        model_version="manual-edit",
    )
    img.messages.append(msg)
    img.active_message = msg

    _record(db, brief, actor, BriefEventKind.banner_image_edited, summary[:255])
    db.commit()
    db.refresh(img)
    db.refresh(msg)
    return img, msg


def approve_images(db: Session, brief: Brief, actor: User) -> list[BannerImage]:
    """Mark every current hero image approved — the gate before Figma export."""
    images = list_images(db, brief.id)
    if not images:
        raise ValueError("no images to approve")
    for img in images:
        img.status = BannerImageStatus.approved.value
    _record(
        db,
        brief,
        actor,
        BriefEventKind.banner_images_approved,
        f"Approved {len(images)} banner image{'s' if len(images) != 1 else ''} for production",
    )
    db.commit()
    for img in images:
        db.refresh(img)
    return images


def submit_for_review(db: Session, brief: Brief, actor: User) -> Brief:
    """Hand the Figma-exported design to the Marketing Lead for creative review —
    the Designer's explicit final action. Requires the banners to have already
    been exported to Figma, since that exported file is what the Marketing Lead
    reviews."""
    if not brief.figma_file_url:
        raise ValueError("Export the banners to Figma before sending for review")
    brief.stage = BriefStage.creative_review.value
    _record(
        db,
        brief,
        actor,
        BriefEventKind.design_submitted,
        "Design submitted — sent to the Marketing Lead for creative review",
    )
    db.commit()
    db.refresh(brief)
    return brief


def list_images(db: Session, brief_id: uuid.UUID) -> list[BannerImage]:
    """All current hero images for the brief, in creative order."""
    return list(
        db.execute(
            select(BannerImage)
            .join(Creative, Creative.id == BannerImage.creative_id)
            .where(BannerImage.brief_id == brief_id)
            .order_by(Creative.position)
        ).scalars()
    )


def get_image(db: Session, brief_id: uuid.UUID, image_id: uuid.UUID) -> BannerImage | None:
    img = db.get(BannerImage, image_id)
    if img is None or img.brief_id != brief_id:
        return None
    return img


def ensure_seed(db: Session, img: BannerImage) -> BannerImage:
    """Guarantee a thread has its original version — its 'initial commit'.

    Images generated before the chat thread existed have no versions; seed
    version 1 from their current bytes so the original is always present and
    selectable, even after later edits.
    """
    if img.messages:
        return img
    seed = BannerImageMessage(
        comment=None,
        prompt=img.prompt,
        data=img.data,
        mime_type=img.mime_type,
        model_version=img.model_version,
    )
    img.messages.append(seed)
    img.active_message = seed
    db.commit()
    db.refresh(img)
    return img


def add_comment(
    db: Session,
    brief: Brief,
    image_id: uuid.UUID,
    comment: str,
    actor: User,
    from_message_id: uuid.UUID | None = None,
    references: list[tuple[bytes, str]] | None = None,
) -> tuple[BannerImage, BannerImageMessage]:
    """Apply a Designer's chat comment as an edit to a hero image.

    The edit branches from ``from_message_id`` (the version the Designer is viewing)
    when given, otherwise from the live version. The refined image becomes the new
    live version: it's appended to the thread, mirrored onto the image (back to
    'pending' for re-review) and selected as active.

    ``references`` are (bytes, mime type) images the Designer attached to this turn —
    the look they're asking for. They steer this one edit and are not stored; the
    version they produce is what's worth keeping.
    """
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("comment is empty")
    img = get_image(db, brief.id, image_id)
    if img is None:
        raise ValueError("image not found")
    ensure_seed(db, img)  # keep the original as version 1 before this edit

    base_png, base_mime = img.data, img.mime_type
    if from_message_id is not None:
        src = next((m for m in img.messages if m.id == from_message_id), None)
        if src is None:
            raise ValueError("version not found")
        base_png, base_mime = src.data, src.mime_type

    # The attached references ride along with the instruction, so "make it look like
    # this" is answered with the look itself rather than a description of it.
    references = references or []
    # Logged because "the reference did nothing" has two very different causes — the
    # images never arrived, or the model ignored them — and they are indistinguishable
    # from the outside.
    logger.info(
        "Hero image edit: image=%s references=%d (%s) comment=%r",
        image_id,
        len(references),
        ", ".join(f"{len(d)}B {m}" for d, m in references) or "none",
        comment[:120],
    )
    # The chat sends the Designer's words verbatim — no brand scaffold, no fidelity
    # preamble, no reference framing. Everything this pipeline used to append competed
    # with the instruction for the model's attention, and an edit is the one place the
    # Designer is already saying exactly what they want. Generation still carries the
    # full brand prompt; see _image_prompt.
    prompt = comment
    # The base's own shape rather than the template's — the Designer may have cropped
    # it by hand since — and the template's resolution tier, without which the reply
    # comes back at the model's default ~1K and the photo softens with every turn.
    config = _hero_image_config(
        aspect=_source_aspect(base_png),
        size=_template_image_size(db, brief.banner_template_id),
    )
    png, mime_type, usage, latency_ms = _edit_png(
        prompt, base_png, base_mime, config, references
    )
    # Hold the frame: the thread's dimensions are set by its base version and never
    # drift, however many turns the Designer takes.
    png, mime_type = _conform_to_source(png, mime_type, base_png)

    img.data = png
    img.prompt = prompt
    img.mime_type = mime_type
    img.status = BannerImageStatus.pending.value
    img.model_version = settings.image_model
    msg = BannerImageMessage(
        comment=comment,
        prompt=prompt,
        data=png,
        mime_type=mime_type,
        model_version=settings.image_model,
    )
    img.messages.append(msg)
    img.active_message = msg

    ai_log_service.record_call(
        db,
        operation="banner_image",
        model=settings.image_model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        latency_ms=latency_ms,
        brief_id=brief.id,
        creative_id=img.creative_id,
        actor_id=actor.id,
        commit=False,
    )
    db.commit()
    db.refresh(img)
    db.refresh(msg)
    return img, msg


def select_version(
    db: Session, brief: Brief, image_id: uuid.UUID, message_id: uuid.UUID
) -> BannerImage:
    """Make a thread version the live one — what the card and Figma export use.

    Mirrors the chosen version's bytes onto the image and resets it to 'pending'
    so the Designer re-approves the switch.
    """
    img = get_image(db, brief.id, image_id)
    if img is None:
        raise ValueError("image not found")
    msg = next((m for m in img.messages if m.id == message_id), None)
    if msg is None:
        raise ValueError("version not found")
    img.data = msg.data
    img.prompt = msg.prompt
    img.mime_type = msg.mime_type
    img.status = BannerImageStatus.pending.value
    img.active_message = msg
    db.commit()
    db.refresh(img)
    return img


def list_messages(db: Session, image_id: uuid.UUID) -> list[BannerImageMessage]:
    """The chat thread for one hero image — base version first, then each edit."""
    return list(
        db.execute(
            select(BannerImageMessage)
            .where(BannerImageMessage.image_id == image_id)
            .order_by(BannerImageMessage.created_at, BannerImageMessage.id)
        ).scalars()
    )


def get_message(
    db: Session, brief_id: uuid.UUID, image_id: uuid.UUID, message_id: uuid.UUID
) -> BannerImageMessage | None:
    msg = db.get(BannerImageMessage, message_id)
    if msg is None or msg.image_id != image_id:
        return None
    img = get_image(db, brief_id, image_id)
    if img is None:
        return None
    return msg
