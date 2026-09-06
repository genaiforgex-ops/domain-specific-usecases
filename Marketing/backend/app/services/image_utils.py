"""Shared helpers for user-uploaded images — validation and PNG normalisation.

Both the Designer's banner-image uploads and the Product Lead's brief reference
images accept whatever a browser/OS hands over and store a single, predictable
format. Keeping the rules here means the two flows never drift apart.
"""

import io

# Kept for messaging only — decoding with Pillow is what actually decides what we
# accept (see normalize_upload_to_png), so this list is the "friendly" set.
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — plenty for a reference, keeps the DB row sane


def normalize_upload_to_png(data: bytes) -> bytes:
    """Decode an uploaded image and re-encode it as a plain PNG.

    Trusting the browser's Content-Type rejected too much real-world input: a
    Mac/iPhone photo arrives as HEIC, some browsers label a JPEG ``image/jpg``,
    and a drag-drop can carry no type at all. Decoding with Pillow instead means
    we accept whatever it can read (PNG, JPEG, WEBP, GIF, BMP, TIFF, and HEIC when
    the platform's plugin is present) and always store a browser-displayable PNG.
    EXIF orientation is honoured so a portrait phone photo isn't stored sideways.
    Raises ValueError with a friendly message when the bytes can't be decoded.
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)  # respect the camera's orientation
            rgb = im.convert("RGB")
            buf = io.BytesIO()
            rgb.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — any decode failure is a bad upload
        raise ValueError(
            "Couldn't read that image. Use a PNG, JPEG or WEBP — HEIC photos "
            "(the default on iPhone/Mac) need to be exported to JPEG or PNG first."
        ) from exc
