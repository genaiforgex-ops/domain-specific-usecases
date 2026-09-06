"""Live vendor due-diligence agent backed by Gemini + Google Search grounding.

This is the real OSINT adapter (the mock lives beside it). Given a vendor
(legal name + official website), it:

  1. Scrapes the vendor site (homepage + policy pages) via website_scraper.
  2. Asks Gemini to perform a full merchant-style due-diligence audit,
     using Google Search grounding so every adverse finding is anchored to
     a live search result rather than model memory.
  3. Returns a BLANK_AUDIT-shaped dict (rich audit). The vendor service
     stores this and derives flat findings + a red-flag score from it.

Design note — why no responseSchema: Gemini rejects combining the Google
Search tool with a forced responseSchema on several model versions (a
likely cause of the earlier attempt silently failing). So we ground the
call and instruct strict JSON in the prompt, then repair + parse. This
works on any Gemini model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from google import genai
from google.genai import types

from app.adapters.osint.blank_audit import blank_audit, merge_defaults
from app.adapters.osint.website_scraper import ScrapeResult, scrape_vendor_site

logger = logging.getLogger(__name__)

_MAX_SCRAPE_CHARS = 15_000
_CALL_TIMEOUT_SECONDS = 120.0

# Output budget for the audit call.
#
# This was 8000 and that was the cause of intermittent empty reports. On a
# thinking model the cap covers reasoning tokens AND every Google-Search
# grounding round, not just the final JSON — a real ICICI run needs ~3.5k
# thinking + ~5.1k answer tokens, so 8000 left nothing to write the audit with.
# The call then returns finish_reason=MAX_TOKENS with response.text EMPTY (not a
# partial object), so _repair_json has nothing to salvage and the run lands as a
# blank audit. Whether a vendor squeaked under the old cap depended on how many
# searches the model ran, which is why the same vendor could pass and then fail
# on a re-run.
_MAX_OUTPUT_TOKENS = int(os.environ.get("OSINT_MAX_OUTPUT_TOKENS", "32000"))

_SYSTEM_INSTRUCTION = (
    "You are the GenAIForge Risk Vendor Due-Diligence Auditor. "
    "You perform third-party vendor background checks before "
    "an onboarding decision. You specialise in zero-hallucination data extraction and "
    "high-stakes risk profiling. You investigate using live Google Search — you do NOT "
    "answer from memory or training data, only from what you find by searching right now. "
    "You are pathological about surfacing adverse signals: sanctions and watchlist hits, "
    "regulatory enforcement, litigation, fraud, money-laundering / illicit-fund indicators, "
    "financial distress, and shell-company / undisclosed-ownership red flags. You verify "
    "policy pages and contact details from the scraped site content provided. You cross-check "
    "GSTIN / CIN / PAN identifiers against the stated business name. You MUST return valid "
    "JSON only — no markdown code fences, no prose outside the JSON object. If a data point "
    "cannot be verified from a real source, leave it empty and never invent case numbers, "
    "dates, or events."
)


def _repair_json(text: str) -> str:
    """Close unbalanced braces/brackets/strings in a truncated JSON blob.

    Ported from the reference app's repairJson — makes a best effort to
    salvage a response that got cut off at max_output_tokens.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()

    repaired = text
    if in_string:
        repaired += '"'
    for _ in range(2):
        repaired = re.sub(r",\s*$", "", repaired)
        repaired = re.sub(r":\s*$", ": null", repaired)
    while stack:
        repaired += stack.pop()
    return repaired


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    # Strip ```json ... ``` fences if the model added them despite instructions.
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    # Trim to the outermost JSON object.
    start = text.find("{")
    if start > 0:
        text = text[start:]
    for candidate in (text, _repair_json(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    logger.warning("Gemini OSINT returned unparseable JSON: %s", raw[:300])
    return None


def _build_prompt(vendor: dict, scrape: ScrapeResult) -> str:
    legal_name = vendor.get("legal_name", "")
    website = vendor.get("website") or scrape.homepage_url or ""
    cin = vendor.get("cin") or ""
    pan = vendor.get("pan") or ""
    country = vendor.get("country") or "IN"

    scraped = scrape.combined_text()[:_MAX_SCRAPE_CHARS] if scrape.ok else ""
    scraped_block = scraped or (
        "Notice: the vendor site could not be scraped. Rely on Google Search to "
        "discover the company's web presence, policies, and identity."
    )

    template = json.dumps(blank_audit(), indent=2)

    return f"""Perform a comprehensive vendor due-diligence audit before onboarding this vendor.

VENDOR UNDER REVIEW:
- Legal name: {legal_name}
- Official website: {website}
- Stated country: {country}
- CIN (if known): {cin or "unknown"}
- PAN (if known): {pan or "unknown"}

SCRAPED SITE CONTENT (homepage + policy pages, may be truncated):
{scraped_block}

INVESTIGATION RULES (use live Google Search for everything except judging the scraped text):
- IDENTITY: Confirm the real operating business behind the website and legal name. Note industry,
  country, business model, and whether the site's own company name matches the legal name given.
- POLICY & LEGITIMACY: From the scraped content, judge whether Terms, Privacy, Refund/Cancellation,
  and Contact pages exist and read as genuine business content (not generic boilerplate/placeholder).
  Populate key_pages and compliance_checks. A missing/placeholder policy or missing contact/address
  is a red flag.
- IDENTITY CROSS-CHECK: Look for GSTIN (15 chars), CIN, or PAN in the scraped content and via search,
  and cross-check them against the business name. Populate compliance_checks.business_registration.
- SANCTIONS & WATCHLISTS: Search the entity and its known directors against UN Security Council
  Consolidated List, OFAC SDN, EU consolidated sanctions, RBI wilful-defaulter list, and Indian
  government blacklists. These apply regardless of home country — always check.
- REGULATORY ACTION: Search for RBI / SEBI / MCA (or the home-country equivalent) enforcement:
  penalty orders, show-cause notices, licence cancellations or suspensions.
- LITIGATION: Search Indian Kanoon and public court records for pending or decided cases involving
  the entity or its directors. Populate legal.litigations.
- ADVERSE MEDIA: Search recent news for fraud, financial irregularities, data breaches, service
  failures, money-laundering ("USDT layering", "proceeds of crime", "AEPS money laundering"), or
  executive misconduct. Populate legal.news.
- FINANCIAL DISTRESS: Search for IBC / NCLT insolvency filings, loan defaults, credit-rating
  downgrades, or statutory-dues defaults (EPF, GST).
- OWNERSHIP / SHELL RISK: Check MCA 'struck-off' status, frequent director changes, disputed
  beneficial ownership, shell-company indicators, and whether any director/owner is a Politically
  Exposed Person (PEP).
- SECURITY & REPUTATION: Assess security headers (HSTS, CSP, X-Frame) and check the domain's
  presence in VirusTotal, AlienVault OTX, AbuseIPDB, and URLScan.io. Populate the security object.
- SOCIAL MEDIA & ONLINE REPUTATION: Find the vendor's official social profiles (LinkedIn, X/Twitter,
  Facebook, Instagram, YouTube). For each capture platform, url, handle, status, and follower count
  if visible. Summarise customer/employee sentiment from Google reviews, Trustpilot, and Glassdoor,
  and set an overall reputation (Positive / Mixed / Negative). Populate the social object
  (profiles[], reputation, review_summary). Treat sparse/absent social presence or strongly negative
  reviews as a risk signal.
- FOOTPRINT: Discover other domains/entities linked by shared contact assets (emails, phones,
  addresses) or shared registration/WHOIS ownership. Populate footprint.
- RISK SYNTHESIS: Produce risk.score (0-100; 0-25 Low, 26-50 Medium, 51-75 High, 76-100 Critical),
  risk.rating, a decision (one of: "Approve", "Approve with Conditions", "Manual Review", "Reject"),
  risk.summary, and explicit green_flags / red_flags / conditions.
- ANTI-HALLUCINATION: If something is not found, report it as not found / empty. Never fabricate
  case numbers, dates, penalties, or events. Populate verification.grounding_score honestly.

OUTPUT FORMAT — return ONLY a single JSON object matching EXACTLY this structure (same keys, fill
the values; use [] or "" where nothing was found):
{template}
"""


def _coerce_list(value, string_key: str) -> list:
    """Coerce a list that may contain bare strings into a list of dicts,
    putting any bare string under `string_key`. Non-list input → []."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({string_key: item})
        elif item is not None:
            out.append({string_key: str(item)})
    return out


def _normalize(audit: dict) -> dict:
    """Coerce the model's list fields into one consistent object shape.

    The model freely returns some arrays as plain strings and some as
    objects. We normalize ONCE here, at the boundary, so every downstream
    consumer (finding-deriver, UI, PDF) sees dicts — instead of each one
    re-implementing string-vs-object guards.
    """
    # key_pages: a bare string is a URL or page name.
    pages = audit.get("key_pages")
    if isinstance(pages, list):
        norm = []
        for p in pages:
            if isinstance(p, dict):
                norm.append(p)
            elif isinstance(p, str):
                is_url = p.startswith("http")
                norm.append({"page": p, "url": p if is_url else "", "status": "", "snapshot": ""})
        audit["key_pages"] = norm

    risk = audit.get("risk")
    if isinstance(risk, dict):
        risk["factors"] = _coerce_list(risk.get("factors"), "detail")

    legal = audit.get("legal")
    if isinstance(legal, dict):
        legal["news"] = _coerce_list(legal.get("news"), "headline")
        legal["litigations"] = _coerce_list(legal.get("litigations"), "summary")

    fp = audit.get("footprint")
    if isinstance(fp, dict):
        fp["discovered_relations"] = _coerce_list(fp.get("discovered_relations"), "entity_name")
        fp["discovered_domains"] = _coerce_list(fp.get("discovered_domains"), "domain")

    social = audit.get("social")
    if isinstance(social, dict):
        social["profiles"] = _coerce_list(social.get("profiles"), "platform")

    return audit


class GeminiOSINTAdapter:
    model_version = os.environ.get("OSINT_MODEL", "gemini-2.5-flash")

    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key)

    async def audit(self, vendor: dict) -> dict:
        website = vendor.get("website") or ""
        scrape = await scrape_vendor_site(website)

        prompt = _build_prompt(vendor, scrape)
        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.0,
            # Fixed seed + temperature 0 makes the model's own output as
            # reproducible as the API allows. The live Google-Search results
            # can still shift run-to-run, so a report is a point-in-time
            # snapshot, not a guaranteed byte-identical re-run.
            seed=42,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )

        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._client.models.generate_content(
                        model=self.model_version,
                        contents=prompt,
                        config=config,
                    ),
                ),
                timeout=_CALL_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception("Gemini OSINT call failed for %s", vendor.get("legal_name"))
            audit = blank_audit()
            audit["_scrape"] = scrape.as_dict()
            audit["risk"]["decision"] = "Manual Review"
            audit["risk"]["summary"] = f"Automated screening failed: {exc}. Manual review required."
            audit["_error"] = str(exc)
            return audit

        raw = getattr(response, "text", "") or ""
        parsed = _extract_json(raw)

        audit = _normalize(merge_defaults(parsed or {}))
        audit["_url"] = website or audit.get("_url", "")
        audit["_scrape"] = scrape.as_dict()
        audit["_model_version"] = self.model_version
        audit["_grounding_sources"] = _grounding_sources(response)
        audit["_usage"] = _usage_tokens(response)

        if parsed is None:
            # Distinguish "ran out of room" from "returned malformed JSON". They
            # look identical downstream but need opposite fixes — raise the
            # output budget vs. tighten the prompt — and the old code reported
            # every truncation as a parse failure.
            truncated = _hit_output_limit(response)
            logger.warning(
                "Gemini OSINT produced no usable audit for %s (finish_reason=%s, text_len=%d)",
                vendor.get("legal_name"),
                _finish_reasons(response),
                len(raw),
            )
            audit["risk"]["decision"] = "Manual Review"
            if truncated:
                audit["_error"] = "truncated_model_response"
                audit["risk"]["summary"] = (
                    "The screening model hit its output limit before completing the audit. "
                    "Manual review required; re-run to retry."
                )
            else:
                audit["_error"] = "unparseable_model_response"
                audit["risk"]["summary"] = (
                    "The screening model did not return a parseable audit. Manual review required."
                )

        return audit

    # Backward-compatible shim: older callers used gather() -> findings.
    async def gather(self, vendor: dict) -> list:
        from app.services.vendor_service import derive_findings_from_audit

        audit = await self.audit(vendor)
        return derive_findings_from_audit(audit)


def _finish_reasons(response) -> list[str]:
    return [str(getattr(c, "finish_reason", "")) for c in (getattr(response, "candidates", None) or [])]


def _hit_output_limit(response) -> bool:
    """True when the model stopped because it ran out of output tokens.

    Checked by name rather than enum identity so a newer SDK renaming or
    re-homing the enum degrades to "not truncated" instead of raising inside the
    error path.
    """
    return any("MAX_TOKENS" in reason for reason in _finish_reasons(response))


def _usage_tokens(response) -> dict:
    """Token counts from the model response, for usage/metrics accounting.

    Returns zeros when the SDK didn't attach usage_metadata.
    """
    usage = getattr(response, "usage_metadata", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_token_count", None) or 0,
        "completion_tokens": getattr(usage, "candidates_token_count", None) or 0,
        "total_tokens": getattr(usage, "total_token_count", None) or 0,
    }


def _grounding_sources(response) -> list[dict]:
    """Extract real source URLs from Gemini grounding metadata, if present."""
    sources: list[dict] = []
    try:
        for cand in getattr(response, "candidates", []) or []:
            meta = getattr(cand, "grounding_metadata", None)
            for chunk in getattr(meta, "grounding_chunks", []) or []:
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    sources.append({"title": getattr(web, "title", ""), "url": web.uri})
    except Exception:  # pragma: no cover - metadata shape is best-effort
        pass
    # Dedupe by url, preserve order.
    seen: set[str] = set()
    deduped = []
    for s in sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        deduped.append(s)
    return deduped
