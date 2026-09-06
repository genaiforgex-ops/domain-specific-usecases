"""Best-effort, bounded scrape of a vendor's public website.

Strategy (matches the M2 VDD design decision):
  1. Jina Reader (https://r.jina.ai/{url}) is tried first — it renders
     JavaScript and returns clean markdown, so single-page-app sites still
     yield text.
  2. If Jina is down / rate-limited / times out, fall back to a direct
     httpx fetch + trafilatura main-text extraction (pure Python, no
     external service).

We fetch the homepage, then follow up to _MAX_POLICY_PAGES discovered
footer/nav links pointing at Terms, Privacy, Refund/Return, Contact, or
About pages — a legitimate business has real ones; a shell company does
not. The combined text is what the Gemini agent reads for its
web-presence / legitimacy judgement.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_JINA_BASE = "https://r.jina.ai/"
_USER_AGENT = "GenAIForge Risk-VendorDD/1.0 (+internal vendor due-diligence check)"
_FETCH_TIMEOUT_SECONDS = 15.0
_MAX_POLICY_PAGES = 5
_MAX_PAGE_CHARS = 8_000
_MIN_USABLE_TEXT = 200  # below this we treat a fetch as "empty"

# Footer/nav links worth following, and the label we show for each.
_POLICY_PATTERNS: list[tuple[str, str]] = [
    (r"privacy", "Privacy Policy"),
    (r"terms(?:\s*(?:&|and)?\s*conditions)?|\btos\b|terms-of-service", "Terms & Conditions"),
    (r"refund|cancellation|return", "Refund / Cancellation"),
    (r"shipping|delivery", "Shipping"),
    (r"contact", "Contact"),
    (r"about", "About"),
]

# Matches markdown links [text](href) and HTML href="..." so we can discover
# policy pages regardless of whether Jina markdown or raw HTML came back.
_LINK_RE = re.compile(r'(?:\]\((?P<md>[^)\s]+)\))|(?:href=["\'](?P<html>[^"\']+)["\'])', re.IGNORECASE)


@dataclass
class ScrapedPage:
    label: str
    url: str
    text: str


@dataclass
class ScrapeResult:
    homepage_url: str
    homepage_text: str
    pages: list[ScrapedPage] = field(default_factory=list)
    method: str = "none"          # "jina" | "httpx" | "none"
    ok: bool = False
    error: str | None = None

    def combined_text(self) -> str:
        """All scraped text, labelled per page, for the agent prompt."""
        chunks = [f"### HOMEPAGE ({self.homepage_url})\n{self.homepage_text}"]
        for p in self.pages:
            chunks.append(f"### {p.label} ({p.url})\n{p.text}")
        return "\n\n".join(chunks)

    def as_dict(self) -> dict:
        return {
            "homepage_url": self.homepage_url,
            "method": self.method,
            "ok": self.ok,
            "error": self.error,
            "pages": [{"label": p.label, "url": p.url} for p in self.pages],
        }


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


async def _fetch_via_jina(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(
        _JINA_BASE + url,
        headers={"X-Return-Format": "markdown", "User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()
    return resp.text


async def _fetch_via_httpx(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Returns (extracted_text, raw_html)."""
    resp = await client.get(url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text
    text = html
    try:
        import trafilatura

        extracted = trafilatura.extract(html) or ""
        if len(extracted) >= _MIN_USABLE_TEXT:
            text = extracted
    except Exception as exc:  # pragma: no cover - trafilatura best-effort
        logger.debug("trafilatura extract failed for %s: %s", url, exc)
    return text, html


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, str, str]:
    """Fetch one page. Returns (text, raw_html_for_link_discovery, method).

    Jina is primary; httpx+trafilatura is the fallback.
    """
    try:
        text = await _fetch_via_jina(client, url)
        if len(text) >= _MIN_USABLE_TEXT:
            return text[:_MAX_PAGE_CHARS], text, "jina"
        logger.info("Jina returned thin content for %s (%d chars); trying httpx", url, len(text))
    except Exception as exc:
        logger.info("Jina fetch failed for %s (%s); falling back to httpx", url, exc)

    text, html = await _fetch_via_httpx(client, url)
    return text[:_MAX_PAGE_CHARS], html, "httpx"


def _discover_policy_links(source: str, base_url: str) -> list[tuple[str, str]]:
    """Find policy/nav links in markdown or HTML. Returns [(label, url)]."""
    base_host = urlparse(base_url).netloc
    found: dict[str, tuple[str, str]] = {}  # label -> (label, url), first hit wins
    for m in _LINK_RE.finditer(source):
        href = m.group("md") or m.group("html")
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        # Stay on the vendor's own domain — don't follow off-site links.
        if urlparse(absolute).netloc and urlparse(absolute).netloc != base_host:
            continue
        target = href.lower()
        for pattern, label in _POLICY_PATTERNS:
            if label in found:
                continue
            if re.search(pattern, target, re.IGNORECASE):
                found[label] = (label, absolute)
                break
    return list(found.values())


async def scrape_vendor_site(url: str) -> ScrapeResult:
    """Scrape a vendor homepage + a bounded set of policy pages."""
    normalized = _normalize_url(url)
    if not normalized:
        return ScrapeResult(homepage_url="", homepage_text="", error="No website URL provided")

    result = ScrapeResult(homepage_url=normalized, homepage_text="")
    timeout = httpx.Timeout(_FETCH_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            home_text, home_source, method = await _fetch_page(client, normalized)
        except Exception as exc:
            logger.warning("Homepage scrape failed for %s: %s", normalized, exc)
            result.error = f"Homepage fetch failed: {exc}"
            return result

        result.homepage_text = home_text
        result.method = method
        result.ok = True

        links = _discover_policy_links(home_source, normalized)[:_MAX_POLICY_PAGES]

        async def _fetch_policy(label: str, link_url: str) -> ScrapedPage | None:
            try:
                page_text, _, _ = await _fetch_page(client, link_url)
                if page_text.strip():
                    return ScrapedPage(label=label, url=link_url, text=page_text)
            except Exception as exc:
                logger.debug("Policy page fetch failed (%s): %s", link_url, exc)
            return None

        # Fetch all policy pages concurrently — wall-clock ≈ slowest page,
        # not the sum of all of them.
        fetched = await asyncio.gather(*[_fetch_policy(lbl, url) for lbl, url in links])
        result.pages = [p for p in fetched if p is not None]

    return result
