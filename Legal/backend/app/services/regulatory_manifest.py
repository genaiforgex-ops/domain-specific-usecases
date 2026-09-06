"""The regulatory corpus manifest — the single source of truth for what the
corpus is supposed to contain.

`backend/config/REGULATORY_CORPUS_MANIFEST.csv` lists every statute, master
direction and circular the bot must be able to cite, with its official URL,
effective date, supersession chain and refresh cadence. Documents are ingested
against a manifest row; nothing enters the corpus without one, which is what
keeps citations traceable to an official source.
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.config import settings

logger = logging.getLogger(__name__)

# Living documents carry this instead of a date — the regulator republishes the
# same URL in place, so there is no single effective date to pin.
CHECK_LATEST = "check-latest"

DOMAINS = (
    "payments_banking",
    "lending_credit",
    "investments_wealth",
    "insurance",
    "data_privacy_cyber",
    "aml_kyc",
    "consumer_protection",
)


class ManifestRow(BaseModel):
    """One row of REGULATORY_CORPUS_MANIFEST.csv."""

    doc_id: str
    domain: str
    title: str
    issuer: str
    doc_type: str
    priority: str = "P3"
    update_cadence: str = "stable"
    download_mode: str = "manual"
    direct_pdf_url: str | None = None
    official_url: str | None = None
    version_or_effective: str = ""
    supersedes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("supersedes", "tags", mode="before")
    @classmethod
    def _split_semicolons(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        raw = str(v or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(";") if part.strip()]

    @field_validator("direct_pdf_url", "official_url", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> str | None:
        raw = str(v or "").strip()
        return raw or None

    @property
    def effective_date(self) -> date | None:
        """Parsed effective date, or None for `check-latest` living documents."""
        raw = (self.version_or_effective or "").strip()
        if not raw or raw.lower() == CHECK_LATEST:
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    @property
    def is_living(self) -> bool:
        """True when the regulator updates this document in place."""
        return (self.version_or_effective or "").strip().lower() == CHECK_LATEST

    @property
    def can_auto_fetch(self) -> bool:
        return self.download_mode == "direct" and bool(self.direct_pdf_url)


class ManifestError(Exception):
    """Raised when the manifest is missing or unusable."""


def _read_rows(path: Path) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for lineno, raw in enumerate(csv.DictReader(fh), start=2):
            doc_id = (raw.get("doc_id") or "").strip()
            if not doc_id:
                continue
            try:
                rows.append(ManifestRow(**{k: v for k, v in raw.items() if k}))
            except Exception as exc:  # noqa: BLE001 - one bad row must not kill the load
                logger.error("Manifest row %s (%s) is invalid: %s", lineno, doc_id, exc)
    return rows


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, ManifestRow]:
    """All manifest rows keyed by doc_id. Cached; call `reload_manifest` after edits."""
    path = Path(settings.regulatory_manifest_file)
    if not path.is_file():
        raise ManifestError(f"Regulatory manifest not found at {path}")

    rows = _read_rows(path)
    if not rows:
        raise ManifestError(f"Regulatory manifest at {path} has no usable rows")

    by_id: dict[str, ManifestRow] = {}
    for row in rows:
        if row.doc_id in by_id:
            logger.error("Duplicate doc_id %s in manifest — keeping the first", row.doc_id)
            continue
        by_id[row.doc_id] = row
    return by_id


def reload_manifest() -> dict[str, ManifestRow]:
    load_manifest.cache_clear()
    return load_manifest()


def manifest_row(doc_id: str) -> ManifestRow | None:
    return load_manifest().get((doc_id or "").strip())


def require_row(doc_id: str) -> ManifestRow:
    row = manifest_row(doc_id)
    if row is None:
        raise ManifestError(f"Unknown doc_id '{doc_id}' — add it to the manifest first")
    return row


def rows_by_priority(*priorities: str) -> list[ManifestRow]:
    wanted = {p.upper() for p in priorities} or None
    return [
        row
        for row in load_manifest().values()
        if wanted is None or row.priority.upper() in wanted
    ]


_HOSTNAME_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")


def official_host(url: str | None) -> str | None:
    """Bare hostname from a manifest URL, or None if it isn't a usable host.

    Some rows carry a human hint rather than a deep link — e.g.
    "https://www.indiacode.nic.in (search: PMLA ...)" — so anything after
    whitespace is dropped and the result is shape-checked.
    """
    raw = (url or "").strip()
    if not raw:
        return None
    host = raw.split("//")[-1].split("/")[0].split()[0].strip().lower()
    host = host.split("?")[0].removeprefix("www.")
    return host if _HOSTNAME_RE.match(host) else None


def issuer_domains() -> dict[str, list[str]]:
    """Official hostnames per domain, for site-scoped primary-source search."""
    out: dict[str, set[str]] = {}
    for row in load_manifest().values():
        host = official_host(row.official_url) or official_host(row.direct_pdf_url)
        if host:
            out.setdefault(row.domain, set()).add(host)
    return {k: sorted(v) for k, v in out.items()}


def all_official_hosts() -> list[str]:
    """Every distinct official hostname in the manifest."""
    hosts: set[str] = set()
    for row in load_manifest().values():
        for candidate in (row.official_url, row.direct_pdf_url):
            host = official_host(candidate)
            if host:
                hosts.add(host)
    return sorted(hosts)
