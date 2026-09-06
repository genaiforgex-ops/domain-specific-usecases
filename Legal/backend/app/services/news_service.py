"""Regulatory Intelligence scraper (UC-06).

For each tracked source we combine two discovery methods and merge the results:
  1. **Fetch** the source page/feed (httpx) and parse it — RSS via ``feedparser``,
     HTML via ``BeautifulSoup`` (best-effort link/headline extraction).
  2. **Web search** scoped to the source's domain (reusing the web-search tool),
     which catches items the raw page doesn't expose (JS-heavy gov sites).

New items (deduped by URL) get their body fetched, are summarized/classified by
the AI seam (``analyse_regulatory_update`` — LLM under the ADK backend, keyword
fallback otherwise), and stored as ``RegulatoryUpdate`` rows. High-relevance
items are marked ``action_required`` and trigger an email alert to the legal team.

All network work is best-effort: a source that times out or blocks bots is
logged in ``last_status`` and skipped, never aborting the whole run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.news import RegulatoryUpdate
from app.models.tracked_source import TrackedSource
from app.orchestrator.tools.web_search import run_web_search
from app.orchestrator import tasks as orch_tasks

logger = logging.getLogger("legalos.news")

_UA = "Mozilla/5.0 (compatible; LegalOS-RegWatch/1.0; +https://legalos.jfpsl)"
_HTTP_TIMEOUT = 20.0
_MAX_ITEMS_PER_SOURCE = 15
_MAX_BODY_CHARS = 20000
_ACTION_RELEVANCE = 0.65  # >= this ⇒ auto-flag action_required


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:  # noqa: BLE001
        return ""


def _norm_url(url: str) -> str:
    """Normalize for dedupe: drop fragment + trailing slash, lowercase host/scheme."""
    try:
        p = urlparse(url.strip())
        path = (p.path or "").rstrip("/")
        return f"{p.scheme.lower()}://{p.netloc.lower()}{path}" + (f"?{p.query}" if p.query else "")
    except Exception:  # noqa: BLE001
        return (url or "").strip().rstrip("/")


def _get(url: str):
    import httpx

    return httpx.get(
        url,
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml,application/xml"},
    )


def fetch_source(source: TrackedSource) -> list[dict]:
    """Fetch + parse a source. Returns ``[{title, url, published_at?, snippet}]``."""
    try:
        resp = _get(source.url)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_source GET failed for %s: %s", source.url, exc)
        raise

    ctype = resp.headers.get("content-type", "").lower()
    is_feed = source.source_type == "rss" or "xml" in ctype or "rss" in ctype
    if is_feed:
        return _parse_feed(resp.content)
    return _parse_html(resp.text, source.url)


def _parse_feed(content: bytes) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed; skipping feed parse")
        return []
    parsed = feedparser.parse(content)
    items: list[dict] = []
    for e in parsed.entries[:_MAX_ITEMS_PER_SOURCE]:
        pub = None
        if getattr(e, "published_parsed", None):
            try:
                pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                pub = None
        items.append(
            {
                "title": (getattr(e, "title", "") or "").strip(),
                "url": (getattr(e, "link", "") or "").strip(),
                "published_at": pub,
                "snippet": (getattr(e, "summary", "") or "").strip()[:500],
            }
        )
    return [i for i in items if i["title"] and i["url"]]


def _parse_html(html: str, base_url: str) -> list[dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup4 not installed; skipping HTML parse")
        return []
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = a["href"].strip()
        # Heuristic: real content links have a meaningful anchor and a document/page href.
        if len(text) < 25 or href.startswith("#") or href.lower().startswith("javascript"):
            continue
        full = urljoin(base_url, href)
        if full in seen:
            continue
        seen.add(full)
        items.append({"title": text[:400], "url": full, "published_at": None, "snippet": ""})
        if len(items) >= _MAX_ITEMS_PER_SOURCE:
            break
    return items


def search_source(source: TrackedSource) -> list[dict]:
    """Domain-scoped web search for recent items from this source."""
    dom = _domain(source.url)
    if not dom:
        return []
    query = f"site:{dom} circular OR notification OR press release OR guidelines OR update"
    return [
        {"title": r["title"], "url": r["href"], "published_at": None, "snippet": r["body"]}
        for r in run_web_search(query)
        if r.get("href")
    ]


def discover(query: str) -> list[dict]:
    """Generic web search for the Discover tab."""
    return [
        {"title": r["title"], "url": r["href"], "snippet": r["body"]}
        for r in run_web_search(query)
        if r.get("href")
    ]


def _fetch_text(url: str) -> str:
    """Best-effort plain-text body of an item page (for summarization)."""
    try:
        from bs4 import BeautifulSoup

        resp = _get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return " ".join(soup.get_text(" ", strip=True).split())[:_MAX_BODY_CHARS]
    except Exception:  # noqa: BLE001
        return ""


def _build_update(
    source: TrackedSource,
    item: dict,
    body: str,
    *,
    db: Session | None = None,
) -> RegulatoryUpdate:
    analysis = orch_tasks.analyse_regulatory_update(
        source.regulator,
        item["title"],
        body or item.get("snippet", ""),
        module="legal_news",
        operation="analyse_regulatory_update",
        db=db,
    )
    status = "action_required" if analysis.relevance_score >= _ACTION_RELEVANCE else "for_information"
    return RegulatoryUpdate(
        source=source.regulator,
        source_id=source.id,
        category=analysis.category,
        title=item["title"][:512],
        summary=analysis.summary or item.get("snippet", "") or item["title"],
        full_text=body or None,
        url=item["url"][:1024],
        tags=analysis.tags,
        relevance_score=analysis.relevance_score,
        status=status,
        impact_note=analysis.impact_note,
        published_at=item.get("published_at") or datetime.now(timezone.utc),
    )


def scrape_source(db: Session, source: TrackedSource) -> dict:
    """Fetch+search a single source, persist new updates. Returns a summary dict."""
    errors: list[str] = []
    items: list[dict] = []
    try:
        items.extend(fetch_source(source))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fetch: {exc}")
    try:
        items.extend(search_source(source))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"search: {exc}")

    # Dedupe within batch and against existing rows (normalized URL).
    existing_urls = {
        _norm_url(u)
        for u in db.execute(
            select(RegulatoryUpdate.url).where(RegulatoryUpdate.url.is_not(None))
        ).scalars().all()
    }
    new_updates: list[RegulatoryUpdate] = []
    batch_seen: set[str] = set()
    for item in items:
        url = item.get("url")
        norm = _norm_url(url) if url else ""
        if not url or not item.get("title") or norm in existing_urls or norm in batch_seen:
            continue
        batch_seen.add(norm)
        body = _fetch_text(url)
        upd = _build_update(source, item, body, db=db)
        db.add(upd)
        new_updates.append(upd)
        if len(new_updates) >= _MAX_ITEMS_PER_SOURCE:
            break

    source.last_fetched_at = datetime.now(timezone.utc)
    source.last_status = (
        f"{len(new_updates)} new" if not errors else f"{len(new_updates)} new; " + "; ".join(errors)[:200]
    )
    db.flush()
    return {"source_id": source.id, "new_count": len(new_updates), "new": new_updates, "errors": errors}


def scrape_all(db: Session, only_source_id: int | None = None) -> dict:
    """Scrape all enabled sources (or one). Persists updates, emails alerts, commits."""
    q = select(TrackedSource).where(TrackedSource.enabled.is_(True))
    if only_source_id is not None:
        q = select(TrackedSource).where(TrackedSource.id == only_source_id)
    sources = db.execute(q).scalars().all()

    total_new = 0
    action_items: list[RegulatoryUpdate] = []
    per_source: list[dict] = []
    for source in sources:
        try:
            res = scrape_source(db, source)
            total_new += res["new_count"]
            action_items.extend([u for u in res["new"] if u.status == "action_required"])
            per_source.append(
                {"source": source.name, "regulator": source.regulator, "new_count": res["new_count"], "errors": res["errors"]}
            )
        except Exception as exc:  # noqa: BLE001 — never let one source kill the run
            logger.exception("scrape_source crashed for %s", source.url)
            per_source.append({"source": source.name, "new_count": 0, "errors": [str(exc)]})
    db.commit()

    # Email the legal team about new action-required items (best-effort).
    if action_items:
        try:
            from app.services.notify_hooks import notify_regulatory_updates

            notify_regulatory_updates(db, action_items)
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("regulatory alert dispatch failed")

    return {"total_new": total_new, "action_required": len(action_items), "sources": per_source}


def save_discovered(
    db: Session,
    *,
    url: str,
    title: str,
    regulator: str,
    category: str | None = None,
    user_id: int | None = None,
) -> RegulatoryUpdate:
    """Persist a user-chosen Discover result as a RegulatoryUpdate."""
    existing = db.execute(
        select(RegulatoryUpdate).where(RegulatoryUpdate.url == url)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    body = _fetch_text(url)
    analysis = orch_tasks.analyse_regulatory_update(
        regulator,
        title,
        body,
        module="legal_news",
        operation="save_discovered",
        user_id=user_id,
        db=db,
    )
    upd = RegulatoryUpdate(
        source=regulator or "Web",
        category=category or analysis.category,
        title=title[:512],
        summary=analysis.summary or title,
        full_text=body or None,
        url=url[:1024],
        tags=analysis.tags,
        relevance_score=analysis.relevance_score,
        status="for_information",
        impact_note=analysis.impact_note,
        published_at=datetime.now(timezone.utc),
    )
    db.add(upd)
    db.flush()
    return upd
