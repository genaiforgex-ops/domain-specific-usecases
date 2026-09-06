"""Load a banner template's reference artwork into the DB.

The Designer picks a template by looking at its sample banner, so every template
row wants a preview image. Templates are seeded by migrations, but their artwork
is a binary asset — this script attaches one (or clears it), which is the CLI
counterpart of `POST /api/banner-templates/{id}/preview`.

Usage (from backend/):
    python -m scripts.set_template_preview --list
    python -m scripts.set_template_preview "Performance statics" ../previews/perf.png
    python -m scripts.set_template_preview <template-uuid> ./sample.jpg
    python -m scripts.set_template_preview "Messaging — WhatsApp / RCS / RPN" --clear

The template can be named by id, exact name, or a unique case-insensitive
substring of its name.
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models.banner_template import BannerTemplate
from app.services import banner_template_service


def _resolve(db, needle: str) -> BannerTemplate:
    """Find a template by id, exact name, or unique name substring."""
    try:
        row = db.get(BannerTemplate, uuid.UUID(needle))
        if row is not None:
            return row
    except ValueError:
        pass  # not a UUID — fall through to name matching

    rows = list(db.scalars(select(BannerTemplate).where(BannerTemplate.name == needle)))
    if not rows:
        rows = list(
            db.scalars(select(BannerTemplate).where(BannerTemplate.name.ilike(f"%{needle}%")))
        )
    if not rows:
        raise SystemExit(f"No banner template matches {needle!r} (try --list)")
    if len(rows) > 1:
        names = ", ".join(r.name for r in rows)
        raise SystemExit(f"{needle!r} matches several templates: {names}")
    return rows[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", nargs="?", help="template id, name, or name substring")
    parser.add_argument("image", nargs="?", help="path to the PNG/JPEG/WEBP sample banner")
    parser.add_argument("--clear", action="store_true", help="remove the template's artwork")
    parser.add_argument("--list", action="store_true", help="list templates and their preview state")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.list:
            for t in banner_template_service.list_templates(db):
                mark = "with preview" if t.preview_image else "NO preview"
                print(f"{t.id}  [{t.category}]  {t.name}  — {mark}")
            return 0

        if not args.template:
            parser.error("name a template (or pass --list)")
        template = _resolve(db, args.template)

        if args.clear:
            banner_template_service.clear_preview(db, template)
            print(f"Cleared the preview image on {template.name!r}")
            return 0

        if not args.image:
            parser.error("pass an image path (or --clear)")
        path = Path(args.image)
        if not path.is_file():
            raise SystemExit(f"No such file: {path}")
        mime = mimetypes.guess_type(path.name)[0] or ""
        try:
            banner_template_service.set_preview(db, template, path.read_bytes(), mime)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        print(f"Set {path.name} ({mime}) as the preview for {template.name!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
