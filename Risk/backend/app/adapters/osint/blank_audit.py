"""Canonical shape of a vendor due-diligence audit.

Mirrors the reference MDD dashboard's BLANK_DATA. Used both as the JSON
template we hand the model (so it returns the exact shape) and as the set
of defaults we merge the model's response into (so every key always
exists, even if the model omits it). Keep this in sync with the frontend
audit renderer.
"""
from __future__ import annotations

import copy

BLANK_AUDIT: dict = {
    "_url": "",
    "_domain": "",
    "business_name": "",
    "business_description": "",
    "industry": "",
    "country": "",
    "ssl_secure": False,
    "mobile_friendly": False,
    "key_pages": [],  # [{page, status, url, snapshot, missing_info[]}]
    "ecom": {"flow_complete": False, "is_service_business": False, "notes": "", "pricing_benchmark": ""},
    "auth": {"notes": ""},
    "payment": {"gateway": "", "confidence": "", "evidence": "", "methods": [], "notes": ""},
    "technical": {
        "platform": "",
        "platform_clues": [],
        "domain_age": "",
        "domain_registered": "",
        "hosting": "",
        "analytics": [],
        "marketing_tools": [],
        "security_headers": {"hsts": False, "csp": False, "xframe": False},
        "notes": "",
    },
    "security": {
        "owasp_posture_score": 0,
        "vapt_findings": [],  # [{category, severity, description, exploitability, impact, recommendation}]
        "ip_reputation": {"score": 0, "sources": []},
        "reputation_sources": {
            "alienvault": {"detections": 0, "status": ""},
            "virustotal": {"detections": 0, "status": ""},
            "abuseipdb": {"detections": 0, "status": ""},
            "urlscan": {"detections": 0, "status": ""},
            "social_risk": {"level": "", "findings": ""},
        },
        "incident_history": [],  # [{date, event, status, summary}]
        "notes": "",
    },
    "social": {"profiles": [], "reputation": "", "review_summary": "", "linkages": []},
    "hidden": {"notes": "", "redirection_check": {"has_hidden_redirects": False, "details": ""}},
    "legal": {
        "news": [],  # [{headline, date, source, url, summary}]
        "litigations": [],  # [{type, status, parties, case_number, court, filing_date, summary}]
        "notes": "",
    },
    "compliance_checks": {
        "legal_placeholders": {"status": "Not Run", "details": ""},
        "copyright_discrepancy": {"status": "Not Run", "details": ""},
        "email_consistency": {"status": "Not Run", "details": ""},
        "business_registration": {
            "status": "Not Run",
            "details": "",
            "registration_id": "",
            "registration_type": "GST",
            "verification_context": "",
        },
        "social_proof": {"status": "Not Run", "details": ""},
        "high_value_risk": {"status": "Not Run", "details": ""},
    },
    "verification": {"grounding_score": 0, "hallucination_check": [], "ai_self_correction_logs": ""},
    "footprint": {
        "contact_assets": {"emails": [], "phones": [], "addresses": []},
        "discovered_relations": [],
        "discovered_domains": [],
    },
    "risk": {
        "score": 0,
        "rating": "None",  # Low | Medium | High | Critical
        "factors": [],  # [{factor, impact, points, detail}]
        "mcc": {"code": "", "description": "", "rationale": ""},
        "mcc_alternatives": [],
        "decision": "None",  # Approve | Approve with Conditions | Reject | Manual Review
        "confidence": "None",
        "summary": "",
        "green_flags": [],
        "red_flags": [],
        "conditions": [],
    },
}


def blank_audit() -> dict:
    return copy.deepcopy(BLANK_AUDIT)


def merge_defaults(data: dict, template: dict | None = None) -> dict:
    """Recursively fill any key missing from `data` using `template`
    (defaults BLANK_AUDIT), so every downstream consumer sees a full shape.
    Lists and scalars from `data` are kept as-is; only missing keys are added.
    """
    if template is None:
        template = BLANK_AUDIT
    out = copy.deepcopy(template)
    if not isinstance(data, dict):
        return out
    for key, tmpl_val in template.items():
        if key not in data or data[key] is None:
            continue
        val = data[key]
        if isinstance(tmpl_val, dict) and isinstance(val, dict):
            out[key] = merge_defaults(val, tmpl_val)
        else:
            out[key] = val
    # Preserve extra keys the model added that aren't in the template.
    for key, val in data.items():
        if key not in template:
            out[key] = val
    return out
