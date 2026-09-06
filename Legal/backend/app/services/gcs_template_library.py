"""Template library backed by GCS.

  Templates (doc_kind=template):
    gs://legalos/legal_templates/…

  Executed legal documents (doc_kind=executed):
    gs://legalos/contracts/…

Both prefixes support a flat layout (existing corpus) or nested
``{contract_type}/{filename}`` for new uploads.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("legalos.templates")

DOC_KINDS = ("template", "executed")
CONTRACT_TYPES = ("MSA", "NDA", "SLA", "Employment", "Policy", "Other")
ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt"}
_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


@dataclass
class LibraryItem:
    name: str
    filename: str
    doc_kind: str
    contract_type: str
    description: str | None
    storage_key: str
    content_type: str | None
    size_bytes: int | None
    updated_at: datetime | None
    source: str = "gcs"


class TemplateLibraryError(RuntimeError):
    pass


def _on_gcp() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))


@lru_cache(maxsize=1)
def _storage_client():
    from google.cloud import storage
    from google.oauth2 import service_account

    creds_file = settings.gcp_service_account_file
    if creds_file and os.path.isfile(creds_file) and not _on_gcp():
        creds = service_account.Credentials.from_service_account_file(creds_file)
        return storage.Client(project=settings.gcp_project_id or None, credentials=creds)
    return storage.Client(project=settings.gcp_project_id or None)


def _bucket():
    name = (settings.legal_templates_bucket or "").strip()
    if not name:
        raise TemplateLibraryError("legal_templates_bucket is not configured")
    return _storage_client().bucket(name)


def templates_prefix() -> str:
    return (settings.legal_templates_prefix or "legal_templates").strip().strip("/")


def contracts_prefix() -> str:
    return (settings.legal_contracts_prefix or "contracts").strip().strip("/")


def prefix_for_kind(doc_kind: str) -> str:
    kind = (doc_kind or "").strip().lower()
    if kind == "executed":
        return contracts_prefix()
    return templates_prefix()


def allowed_prefixes() -> tuple[str, ...]:
    return (templates_prefix(), contracts_prefix())


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\- ()]+", "_", base).strip("._ ")
    return cleaned or "document.bin"


def validate_categories(doc_kind: str, contract_type: str) -> tuple[str, str]:
    kind = (doc_kind or "").strip().lower()
    ctype = (contract_type or "").strip()
    if kind not in DOC_KINDS:
        raise TemplateLibraryError(
            f"doc_kind must be one of: {', '.join(DOC_KINDS)}"
        )
    match = next((c for c in CONTRACT_TYPES if c.lower() == ctype.lower()), None)
    if match is None:
        raise TemplateLibraryError(
            f"contract_type must be one of: {', '.join(CONTRACT_TYPES)}"
        )
    return kind, match


def object_path(doc_kind: str, contract_type: str, filename: str) -> str:
    """Path for new uploads: ``{prefix}/{contract_type}/{filename}``."""
    kind, ctype = validate_categories(doc_kind, contract_type)
    return f"{prefix_for_kind(kind)}/{ctype}/{_safe_filename(filename)}"


def _meta(blob) -> dict[str, str]:
    return dict(blob.metadata or {})


def _infer_contract_type(filename: str) -> str:
    n = filename.lower()
    if "nda" in n:
        return "NDA"
    if "sla" in n or "service level" in n:
        return "SLA"
    if "employment" in n or "offer letter" in n:
        return "Employment"
    if "policy" in n:
        return "Policy"
    if any(
        k in n
        for k in (
            "msa",
            "master service",
            "service provider",
            "service agreement",
            "services agreement",
            "partner service",
            "outsourcing",
            "lsp agreement",
            "it services agreement",
            "subscription",
            "creative agency",
            "novation",
        )
    ):
        return "MSA"
    return "Other"


def _kind_from_key(storage_key: str) -> str | None:
    parts = storage_key.strip("/").split("/")
    if not parts:
        return None
    root = parts[0]
    if root == contracts_prefix():
        return "executed"
    if root == templates_prefix():
        return "template"
    return None


def _item_from_blob(blob) -> LibraryItem | None:
    """Parse blobs under ``legal_templates/`` or ``contracts/`` (flat or typed)."""
    key = blob.name.strip("/")
    parts = key.split("/")
    if len(parts) < 2:
        return None

    root, *rest = parts
    if root == contracts_prefix():
        doc_kind = "executed"
    elif root == templates_prefix():
        doc_kind = "template"
    else:
        return None

    if not rest or not rest[-1] or rest[-1].endswith("/"):
        return None

    # Optional nested type folder: {prefix}/{contract_type}/{file…}
    if len(rest) >= 2 and rest[0] in CONTRACT_TYPES:
        contract_type = rest[0]
        filename = "/".join(rest[1:])
    # Legacy nested kind/type under templates only
    elif (
        root == templates_prefix()
        and len(rest) >= 3
        and rest[0].lower() in DOC_KINDS
    ):
        doc_kind = rest[0].lower()
        contract_type = rest[1] if rest[1] in CONTRACT_TYPES else _infer_contract_type(
            "/".join(rest[2:])
        )
        filename = "/".join(rest[2:])
    else:
        filename = "/".join(rest)
        contract_type = _infer_contract_type(filename)

    if not filename:
        return None

    meta = _meta(blob)
    name = meta.get("display_name") or Path(filename).stem
    description = meta.get("description") or None
    updated = blob.updated
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return LibraryItem(
        name=name,
        filename=filename,
        doc_kind=(meta.get("doc_kind") or doc_kind).lower(),
        contract_type=meta.get("contract_type") or contract_type,
        description=description,
        storage_key=blob.name,
        content_type=blob.content_type,
        size_bytes=blob.size,
        updated_at=updated,
        source="gcs",
    )


def _list_prefix(prefix: str) -> list[LibraryItem]:
    bucket = _bucket()
    items: list[LibraryItem] = []
    root = prefix.strip("/") + "/"
    for blob in bucket.list_blobs(prefix=root):
        if blob.name.endswith("/"):
            continue
        ext = Path(blob.name).suffix.lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            continue
        item = _item_from_blob(blob)
        if item is not None:
            items.append(item)
    return items


def list_library(
    *,
    doc_kind: str | None = None,
    contract_type: str | None = None,
) -> list[LibraryItem]:
    """List templates and/or executed contracts from their GCS prefixes."""
    kind_filter: str | None = None
    type_filter: str | None = None
    if doc_kind:
        kind_filter = doc_kind.strip().lower()
        if kind_filter not in DOC_KINDS:
            raise TemplateLibraryError(f"doc_kind must be one of: {', '.join(DOC_KINDS)}")
    if contract_type:
        type_filter = next(
            (c for c in CONTRACT_TYPES if c.lower() == contract_type.strip().lower()),
            None,
        )
        if type_filter is None:
            raise TemplateLibraryError(
                f"contract_type must be one of: {', '.join(CONTRACT_TYPES)}"
            )

    if kind_filter == "template":
        items = _list_prefix(templates_prefix())
    elif kind_filter == "executed":
        items = _list_prefix(contracts_prefix())
    else:
        items = _list_prefix(templates_prefix()) + _list_prefix(contracts_prefix())

    if type_filter:
        items = [i for i in items if i.contract_type.lower() == type_filter.lower()]

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    items.sort(key=lambda x: (x.updated_at or epoch, x.name), reverse=True)
    return items


def upload_library_file(
    *,
    data: bytes,
    filename: str,
    doc_kind: str,
    contract_type: str,
    name: str | None = None,
    description: str | None = None,
) -> LibraryItem:
    """Upload into ``legal_templates/…`` or ``contracts/…`` by doc_kind."""
    if not data:
        raise TemplateLibraryError("Empty file")
    if len(data) > settings.max_upload_bytes:
        raise TemplateLibraryError(
            f"File exceeds max size ({settings.max_upload_bytes} bytes)"
        )

    kind, ctype = validate_categories(doc_kind, contract_type)
    safe = _safe_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise TemplateLibraryError(
            f"Unsupported file type {ext or '(none)'}. Allowed: docx, pdf, txt"
        )

    path = object_path(kind, ctype, safe)
    bucket = _bucket()
    blob = bucket.blob(path)
    if blob.exists():
        stem, suffix = Path(safe).stem, Path(safe).suffix
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        path = object_path(kind, ctype, f"{stem}_{stamp}{suffix}")
        blob = bucket.blob(path)

    display = (name or Path(safe).stem).strip() or Path(safe).stem
    blob.metadata = {
        "doc_kind": kind,
        "contract_type": ctype,
        "display_name": display[:256],
        "description": (description or "")[:1000],
        "original_filename": Path(filename).name[:256],
    }
    blob.upload_from_string(data, content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"))
    blob.reload()
    item = _item_from_blob(blob)
    if item is None:
        raise TemplateLibraryError("Upload succeeded but object path could not be parsed")
    logger.info("Uploaded library object gs://%s/%s", bucket.name, path)
    return item


def library_categories() -> dict[str, Any]:
    return {
        "doc_kinds": [
            {"id": "template", "label": "Template"},
            {"id": "executed", "label": "Executed legal document"},
        ],
        "contract_types": list(CONTRACT_TYPES),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        "bucket": settings.legal_templates_bucket,
        "prefix": templates_prefix(),
        "templates_prefix": templates_prefix(),
        "contracts_prefix": contracts_prefix(),
    }


def _assert_library_key(storage_key: str) -> str:
    """Reject keys outside legal_templates/ or contracts/."""
    key = (storage_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/"):
        raise TemplateLibraryError("Invalid storage_key")
    if _kind_from_key(key) is None:
        raise TemplateLibraryError(
            "storage_key must be under legal_templates/ or contracts/"
        )
    return key


def download_library_bytes(storage_key: str) -> tuple[bytes, LibraryItem]:
    key = _assert_library_key(storage_key)
    bucket = _bucket()
    blob = bucket.blob(key)
    if not blob.exists():
        raise TemplateLibraryError("Document not found in template library")
    blob.reload()
    item = _item_from_blob(blob)
    if item is None:
        raise TemplateLibraryError("Document path could not be parsed")
    data = blob.download_as_bytes()
    return data, item


def preview_library_text(storage_key: str, *, max_chars: int = 80_000) -> dict[str, Any]:
    from app.services.document_parser import DocumentParseError, parse_document

    data, item = download_library_bytes(storage_key)
    if not data:
        raise TemplateLibraryError("Document is empty")
    try:
        text = parse_document(data, item.filename, item.content_type)
    except DocumentParseError as exc:
        raise TemplateLibraryError(f"Could not extract text: {exc}") from exc

    truncated = len(text) > max_chars
    return {
        "name": item.name,
        "filename": item.filename,
        "doc_kind": item.doc_kind,
        "contract_type": item.contract_type,
        "storage_key": item.storage_key,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "text": text[:max_chars],
        "char_count": len(text),
        "truncated": truncated,
    }


def _normalize_match_key(value: str) -> str:
    s = (value or "").strip().lower()
    if s.startswith("executed:"):
        s = s[len("executed:") :].strip()
    # Drop common extensions for stem matching.
    for ext in ALLOWED_EXTENSIONS:
        if s.endswith(ext):
            s = s[: -len(ext)]
            break
    return re.sub(r"[\s_\-]+", " ", s).strip()


_index_cache: dict[str, Any] | None = None
_index_cache_at: float = 0.0
_INDEX_TTL_SEC = 120.0


def _library_name_index() -> dict[str, tuple[str, str]]:
    """Map normalized filename/stem → (kind, storage_key). Cached briefly."""
    import time

    global _index_cache, _index_cache_at
    now = time.monotonic()
    if _index_cache is not None and (now - _index_cache_at) < _INDEX_TTL_SEC:
        return _index_cache  # type: ignore[return-value]

    index: dict[str, tuple[str, str]] = {}
    try:
        for item in _list_prefix(templates_prefix()) + _list_prefix(contracts_prefix()):
            kind = "executed" if item.doc_kind == "executed" else "template"
            key = item.storage_key
            for raw in (item.filename, Path(item.filename).stem, item.name):
                nk = _normalize_match_key(raw)
                if nk and nk not in index:
                    index[nk] = (kind, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("library name index build failed: %s", exc)

    _index_cache = index
    _index_cache_at = now
    return index


def resolve_library_key_from_rag(
    display_name: str | None,
    source_uri: str | None,
) -> tuple[str, str] | None:
    """Map a Vertex RAG hit to ``(kind, storage_key)`` when possible.

    ``kind`` is ``template`` or ``executed``. Returns None if unresolved.
    """
    uri = (source_uri or "").strip()
    bucket = (settings.legal_templates_bucket or "legalos").strip()
    # gs://legalos/legal_templates/… or gs://legalos/contracts/…
    m = re.match(
        rf"^gs://{re.escape(bucket)}/(?P<key>(?:{re.escape(templates_prefix())}|{re.escape(contracts_prefix())})/.+)$",
        uri,
        flags=re.IGNORECASE,
    )
    if m:
        key = m.group("key")
        kind = _kind_from_key(key) or "template"
        return ("executed" if kind == "executed" else "template", key)

    name = (display_name or "").strip()
    if not name and uri:
        name = Path(uri).name
    if not name:
        return None

    prefer_executed = name.lower().startswith("executed:")
    nk = _normalize_match_key(name)
    if not nk:
        return None

    index = _library_name_index()
    hit = index.get(nk)
    if hit:
        return hit

    # Partial: longest stem containment (conservative).
    best: tuple[str, str] | None = None
    best_len = 0
    for cand, mapped in index.items():
        if prefer_executed and mapped[0] != "executed":
            continue
        if not prefer_executed and mapped[0] != "template":
            # Prefer templates first for non-executed names; allow executed fallback later.
            pass
        if nk in cand or cand in nk:
            if len(cand) > best_len:
                best = mapped
                best_len = len(cand)
    if best:
        return best

    if not prefer_executed:
        # Second pass: allow executed matches for plain names.
        for cand, mapped in index.items():
            if mapped[0] != "executed":
                continue
            if nk in cand or cand in nk:
                if len(cand) > best_len:
                    best = mapped
                    best_len = len(cand)
        if best:
            return best

    return None
