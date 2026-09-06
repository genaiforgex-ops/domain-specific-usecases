"""Deterministic query routing for legal retrieval.

Decides which corpora to search, which regulatory domain to narrow to, and whether
the caller is asking about historical (superseded) law — from keywords and the
manifest's own tags. No LLM call: the agent already chooses its tools, and this only
narrows filters, so spending a model round-trip here would add latency and a failure
mode for no accuracy gain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.services.regulatory_manifest import DOMAINS, issuer_domains, load_manifest

# Words that reliably indicate a domain even when no manifest tag matches.
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "payments_banking": (
        "upi", "ppi", "prepaid", "wallet", "payment aggregator", "payment gateway",
        "bbps", "bharat billpay", "imps", "neft", "rtgs", "autopay", "mandate",
        "settlement", "nodal account", "escrow", "payment system", "banking regulation",
    ),
    "lending_credit": (
        "digital lending", "loan", "lending", "kfs", "key fact statement", "apr",
        "cooling-off", "cooling off", "dlg", "default loss guarantee", "lsp",
        "lending service provider", "recovery agent", "fair practices", "nbfc",
        "disbursal", "foreclosure", "moratorium",
    ),
    "investments_wealth": (
        "mutual fund", "sebi", "nfo", "demat", "depository", "broking", "broker",
        "investment adviser", "portfolio", "aum", "ria", "securities", "distributor commission",
    ),
    "insurance": (
        "insurance", "irdai", "policyholder", "corporate agent", "premium",
        "insurer", "claim settlement", "surrender value",
    ),
    "data_privacy_cyber": (
        "dpdp", "data protection", "personal data", "consent manager", "data fiduciary",
        "data principal", "privacy", "cert-in", "cyber", "breach", "spdi",
        "information technology act", "it rules", "intermediary", "grievance officer",
    ),
    "aml_kyc": (
        "kyc", "aml", "pmla", "money laundering", "v-cip", "vcip", "video kyc",
        "ckyc", "beneficial owner", "str", "suspicious transaction", "ctr",
        "re-kyc", "customer due diligence", "cdd", "pep",
    ),
    "consumer_protection": (
        "consumer", "ombudsman", "grievance", "complaint", "unfair trade",
        "customer rights", "redressal", "deficiency in service",
    ),
}

# Asking about the law as it used to be — the only case where superseded text helps.
_HISTORICAL_RE = re.compile(
    r"\b(?:before\s+(?:19|20)\d{2}|prior\s+to|earlier\s+(?:rule|guideline|direction|version)"
    r"|repealed|superseded|erstwhile|previous\s+(?:rule|guideline|direction|version)"
    r"|used\s+to\s+(?:be|say|require)|history\s+of|历史)\b",
    re.IGNORECASE,
)

# Wants something newer than any static corpus can hold.
_RECENCY_RE = re.compile(
    r"\b(?:latest|newest|current|recent(?:ly)?|this\s+(?:week|month|year)|today|yesterday"
    r"|breaking|just\s+(?:issued|released|announced)|any\s+update|new\s+circular)\b",
    re.IGNORECASE,
)

# Points at JFPSL's own paper rather than the law.
_INTERNAL_RE = re.compile(
    r"\b(?:our|we|jfpsl|jio|internal|template|playbook|msa|nda|sla|standard\s+clause"
    r"|executed|signed|counterparty|vendor|negotiat\w*|draft\w*|redline)\b",
    re.IGNORECASE,
)

# Points at the statute book.
_LAW_RE = re.compile(
    r"\b(?:rbi|sebi|irdai|npci|meity|cert-in|master\s+direction|circular|notification"
    r"|regulation|section|clause|para(?:graph)?|rule|act|statute|guideline|directions?"
    r"|compliance|regulator\w*|permitted|mandat\w*|prescrib\w*|require[sd]?\s+by\s+law)\b",
    re.IGNORECASE,
)


@dataclass
class RouteDecision:
    """Which sources to search for a query, and how to filter them."""

    domains: list[str] = field(default_factory=list)
    use_regulatory: bool = True
    use_jfpsl: bool = False
    needs_web: bool = False
    include_superseded: bool = False
    site_hosts: list[str] = field(default_factory=list)
    matched_tags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = []
        if self.use_regulatory:
            parts.append(
                "regulatory corpus"
                + (f" ({', '.join(self.domains)})" if self.domains else "")
            )
        if self.use_jfpsl:
            parts.append("JFPSL templates")
        if self.needs_web:
            parts.append(
                "primary-source sites"
                + (f" ({', '.join(self.site_hosts[:4])})" if self.site_hosts else "")
            )
        if self.include_superseded:
            parts.append("including superseded law")
        return "; ".join(parts) or "no sources selected"


@lru_cache(maxsize=1)
def _tag_index() -> dict[str, set[str]]:
    """Manifest tag → domains that use it."""
    index: dict[str, set[str]] = {}
    for row in load_manifest().values():
        for tag in row.tags:
            token = tag.strip().lower()
            if token:
                index.setdefault(token, set()).add(row.domain)
    return index


def _score_domains(text: str) -> tuple[list[str], list[str]]:
    """(domains, matched tags) ranked by how many signals hit."""
    lowered = f" {text.lower()} "
    scores: dict[str, int] = {}
    matched: list[str] = []

    for tag, domains in _tag_index().items():
        # Tags are short slugs like "cooling-off"; match the phrase either way.
        needle = tag.replace("-", " ")
        if tag in lowered or (len(needle) > 3 and needle in lowered):
            matched.append(tag)
            for domain in domains:
                scores[domain] = scores.get(domain, 0) + 2

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for word in keywords:
            if word in lowered:
                scores[domain] = scores.get(domain, 0) + 3

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [d for d, _ in ranked if d in DOMAINS], sorted(set(matched))


def route_query(text: str) -> RouteDecision:
    """Classify a query into sources + filters. Never raises."""
    query = (text or "").strip()
    if not query:
        return RouteDecision(use_regulatory=False)

    domains, matched = _score_domains(query)
    historical = bool(_HISTORICAL_RE.search(query))
    recency = bool(_RECENCY_RE.search(query))
    internal = bool(_INTERNAL_RE.search(query))
    legal = bool(_LAW_RE.search(query)) or bool(domains)

    # Only narrow when the signal is clear; a weak guess would hide relevant law.
    top_domains = domains[:2] if domains else []

    hosts: list[str] = []
    if top_domains:
        per_domain = issuer_domains()
        for domain in top_domains:
            hosts.extend(per_domain.get(domain, []))
    if recency and not hosts:
        from app.services.regulatory_manifest import all_official_hosts

        hosts = all_official_hosts()

    return RouteDecision(
        domains=top_domains,
        use_regulatory=legal or not internal,
        use_jfpsl=internal or not legal,
        needs_web=recency,
        include_superseded=historical,
        site_hosts=sorted(dict.fromkeys(hosts)),
        matched_tags=matched,
    )
