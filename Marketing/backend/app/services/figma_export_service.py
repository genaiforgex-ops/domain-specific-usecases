"""Figma export — turn approved hero images + creatives into a Figma file.

Creates a fresh Figma file, uploads each creative's approved hero image (image
hashes are per-file, so they must be re-uploaded into the new file), then
renders the five ad sizes per creative via the on-brand template. The brief is
stamped with the resulting file key/URL for the audit trail. This alone does
NOT hand the design off — the Designer reviews the file, then explicitly sends
it for creative review (see banner_image_service.submit_for_review).
"""

import logging
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.banner_image import BannerImageStatus
from app.models.brief import Brief
from app.models.brief_event import BriefEventKind
from app.models.user import User
from app.services import banner_template_service
from app.services.brief_service import _record
from app.services.figma import mcp_client, render, token_store

logger = logging.getLogger("uvicorn.error")

# Re-exported so the API layer can map auth failures to a 409 without importing
# the client module directly.
FigmaAuthError = mcp_client.FigmaAuthError
FigmaMCPError = mcp_client.FigmaMCPError


def _footer(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    return text or fallback


def export_to_figma(
    db: Session,
    brief: Brief,
    actor: User,
    file_name: str,
    template_id: uuid.UUID | None = None,
    sizes: list[str] | None = None,
) -> dict:
    """Create the Figma file and push every approved creative's banners into it,
    rendered with the chosen banner template (the default when `template_id` is
    None; falls back to the built-in template if none is stored yet). `sizes`
    limits the export to a subset of the template's ad sizes (None = all).

    Returns {"file_key", "file_url", "creatives", "sizes"}."""
    creatives = [
        c
        for c in brief.creatives
        if c.banner_image and c.banner_image.status == BannerImageStatus.approved.value
    ]
    if not creatives:
        raise ValueError("Approve the banner images before exporting to Figma")

    # Resolve the template up front so a bad template_id fails before any Figma
    # call. `bundle` carries the brand system, sizes, strips and render program.
    _template, bundle = banner_template_service.resolve_bundle(db, template_id)

    # Limit to the Designer's selected sizes, preserving the template's order.
    selected_sizes = bundle.sizes
    if sizes:
        wanted = set(sizes)
        unknown = wanted - {s["name"] for s in bundle.sizes}
        if unknown:
            raise ValueError(f"Unknown ad size(s) for this template: {', '.join(sorted(unknown))}")
        selected_sizes = [s for s in bundle.sizes if s["name"] in wanted]
    if not selected_sizes:
        raise ValueError("Select at least one ad size to export")

    name = file_name.strip() or (brief.project_name or brief.product_name or f"Brief {brief.id}")

    # Use the acting Designer's OWN Figma connection — never a shared token.
    oauth = token_store.load(db, actor.id)
    client = mcp_client.connect(oauth, save=lambda o: token_store.save(db, actor.id, o))
    created = mcp_client.create_file(client, name)
    file_key = created["file_key"]

    # Upload each approved hero once (image hashes are per-file) and shape it into
    # a content dict; `col` positions it as a column in the render grid.
    batch = []
    for i, creative in enumerate(creatives):
        img = creative.banner_image
        image_hash = mcp_client.upload_image(client, file_key, img.data, img.mime_type)
        content = render.make_content(
            headline=creative.headline,
            body=creative.body,
            cta=creative.cta or "Learn More",
            image_hash=image_hash,
            footer_left=_footer(creative.entity_attribution, bundle.footer_left),
            footer_right=_footer(creative.terms, bundle.footer_right),
        )
        content["col"] = i
        batch.append(content)

    # One use_figma call per size: only that size's brand strip is embedded, so
    # every payload stays under use_figma's 50k-char code limit. The first size
    # clears the page (removing the auto-placed upload frames) and draws the header.
    for si, size in enumerate(selected_sizes):
        code = render.build_figma_code(bundle, batch, size, clear=(si == 0), header=(si == 0))
        if len(code) > render.CODE_LIMIT:
            raise FigmaMCPError(
                f"Figma render code for size {size['name']} is {len(code)} chars > "
                f"{render.CODE_LIMIT} use_figma limit — reduce embedded asset size."
            )
        result = mcp_client.render_creative(
            client, file_key, code, f"{size['name']} ({size['w']}x{size['h']}) x {len(batch)} copies"
        )
        logger.info("Rendered size %s into %s: %s", size["name"], file_key, result)

    brief.figma_file_key = file_key
    brief.figma_file_url = created["file_url"]
    brief.figma_exported_at = func.now()
    # Export alone doesn't hand the design off — the Designer reviews the Figma
    # file first, then explicitly sends it for creative review (submit_for_review).
    _record(
        db,
        brief,
        actor,
        BriefEventKind.figma_exported,
        f"Exported {len(creatives)} creative{'s' if len(creatives) != 1 else ''} "
        f"× {len(selected_sizes)} sizes to Figma file '{name}'",
    )
    db.commit()
    db.refresh(brief)
    return {
        "file_key": file_key,
        "file_url": created["file_url"],
        "creatives": len(creatives),
        "sizes": len(selected_sizes),
    }
