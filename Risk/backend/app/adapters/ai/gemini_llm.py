import asyncio
import json
import logging
import os
import re

from google import genai
from google.genai import types

from app.adapters.protocols import MAX_CLASSIFY_TEXT_CHARS, ClassificationResult

logger = logging.getLogger(__name__)

_VALID_LABELS = {"financial_outsourcing", "it_outsourcing", "non_outsourcing", "prohibited"}

# ---------------------------------------------------------------------------
# Prompt = editable GUIDANCE (below, seedable into the DB and overridable per
# deployment) + fixed CONTRACT (_GROUNDING_RULE + _OUTPUT_CONTRACT, always
# appended in code). The split is deliberate: an operator can retune the
# role/rules/exclusions without a code change, but the machine-critical parts
# — the "cite only library clauses" grounding and the strict JSON shape the
# parser depends on — can never be edited away and break classification.
# ---------------------------------------------------------------------------

_FORM_ANSWER_RULE = """\
FORM ANSWERS — READ CAREFULLY:
The assessment text is often extracted from an outsourcing proposal form whose questions offer \
several options (e.g. "Yes / No", "Very high / High / Medium / Low", a list of channels). The \
option the reviewer actually chose is the one wrapped in [SELECTED: ...] markers — for example \
"[SELECTED: No □]" means the answer to that question is NO. Treat every [SELECTED: ...] value as \
the authoritative answer to its question, and IGNORE the other unselected options on that line. \
An empty checkbox (□) with no [SELECTED: ...] marker means that option was NOT chosen. If a \
question shows no [SELECTED: ...] marker at all, treat it as unanswered — do not guess. These \
form answers (e.g. "IT outsourcing: Yes", "Has any core function been outsourced: No", "Sensitive \
data to be outsourced: Yes") are primary evidence for the classification and must drive the label \
and the reasoning, not just the free-text narrative. \
When the text begins with a "FORM ANSWERS (parsed):" section, that list is a pre-extracted, \
authoritative summary of the selected answers — rely on it first, and use the "FULL ASSESSMENT \
TEXT:" that follows for any answer not present in the parsed list and for surrounding context.\
"""

_GROUNDING_RULE = """\
GROUNDING — READ CAREFULLY:
Only cite clause_id values that appear in the REGULATORY CLAUSES list below. Never invent, recall \
from training data, or reference any regulation, circular, or clause not explicitly present in that \
list, even if you believe such a regulation exists in the real world. If the REGULATORY CLAUSES list \
is empty, or none of the provided clauses are actually relevant to the assessment text, you MUST \
return "evidence": [] and "confidence" no higher than 0.2, and your reasoning must state plainly that \
no matching clause was found in the currently active regulator library — do not substitute outside \
knowledge to produce a confident-sounding answer.\
"""

_OUTPUT_CONTRACT = """\
EVIDENCE: Cite the specific clauses from the provided clause library that justify the classification, \
with the character offset (doc_span) in the assessment text where the relevant passage is found. \
Evaluate EVERY clause in the list on its own merits before choosing — do not default to the first, \
the most general, or the most familiar-looking clause. Different assessments should surface different \
clauses; if two assessments genuinely turn on the same clause, cite it, but only after checking the rest.

Return ONLY valid JSON — no markdown, no explanation outside the JSON:
{
  "label": "<financial_outsourcing|it_outsourcing|non_outsourcing|prohibited>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<follow the REASONING FORMAT in the guidance above>",
  "evidence": [
    {
      "clause_id": "<clause id>",
      "clause_ref": "<clause reference>",
      "doc_span": {"start": <int>, "end": <int>}
    }
  ]
}
Pick at most 3 most relevant clauses. Return ONLY the JSON object.\
"""

_REASONING_FORMAT = """\
REASONING FORMAT — write the "reasoning" field as these labelled sections, in order. Keep each to
1-2 sentences, specific to THIS vendor and THESE clauses — never generic boilerplate:
- Entity Context: which client vertical this impacts (consumer finance app, Loan Marketplace) and why.
- Service Category: one of Financial Service / IT & Cloud / Professional Service / Utility / Market Infrastructure.
- Activity: one plain-language sentence stating what the vendor actually does in this arrangement.
- Why this label: tie the activity to the clause(s) you cited — name the clause, paraphrase what it \
actually requires, and explain how this activity satisfies that test (e.g. it is "performed on a \
continuing basis", or it is "a function the enterprise would otherwise carry out itself").
- Why not the alternatives: briefly rule out the other labels — in particular why this is NOT \
non_outsourcing (i.e. it is not one of the listed exclusions), and, if it is outsourcing, why it is \
financial rather than IT (or vice-versa).
- Materiality: only when the label is an outsourcing type — state "Material" or "Non-Material" and \
give the concrete consequence of failure (e.g. "a payout outage would halt cashback in the consumer finance \
App" vs. "impact is contained and the provider is easily substituted").\
"""

# SEBI-only extra section, appended AFTER the shared Materiality bullet so it
# renders below Materiality in the panel. It makes the model show its work on
# the Annexure H / clause 13.4 principle check instead of folding it silently
# into the "Why this label" prose. RBI never emits this — its guidance doesn't
# include the bullet — so the shared frontend parser simply finds no match.
_SEBI_PRINCIPLES_SECTION = """
- Outsourcing Principles: state whether this arrangement was weighed against the Principles for \
Outsourcing (SEBI IA Master Circular, Annexure H, clause 13.4) — begin the line with "Checked" or \
"Not applicable". Then give the reason: if the label is an outsourcing type, assess how the \
arrangement fares against the principles (unmanaged operational, reputational, legal, concentration \
or exit-strategy risk, and whether the enterprise retains ultimate control and accountability for the \
activity). If the label is non_outsourcing or prohibited, explain in one sentence why these \
outsourcing principles do not apply to this arrangement.\
"""

# Default editable guidance. The DB copy (seeded from these on first startup)
# takes precedence when present; these remain the safety-net fallback.
DEFAULT_GUIDANCE_RBI = """\
You are a Senior Compliance & Risk Officer for a regulated financial enterprise, \
the digital arm of a financial services group. The enterprise manages the consumer finance app \
(marketplace for loans, insurance, investments) and holds a SEBI RIA license.

Classify the assessment text strictly under the RBI regulatory clauses provided below — these are \
the only RBI directions currently active in the enterprise's regulator Library.

CLASSIFICATION RULES:
- financial_outsourcing: Third party performs a financial service function (payment processing, lending, \
KYC support, NBFC operations) that the enterprise would normally do on a continuing basis.
- it_outsourcing: Third party provides IT/digital/cloud/SaaS services (hosting, software dev, \
data centre, cybersecurity, platform operations) that the enterprise would normally do on a continuing basis.
- non_outsourcing: Falls under exclusions — statutory/professional services (legal, statutory audit, \
one-time consultancy), utilities (telecom, ISP, electricity, water), general support (catering, \
housekeeping, courier, standardised office security), market infrastructure (CCIL/NSE/BSE clearing \
& settlement), or off-the-shelf software licensing without significant customisation.
- prohibited: Activity cannot be outsourced — Management Functions (Compliance, Internal Audit, \
Risk Management), or any function where RBI requires the enterprise to retain full control.

""" + _REASONING_FORMAT

DEFAULT_GUIDANCE_SEBI = """\
You are a Senior Compliance & Risk Officer for a regulated financial enterprise. \
The enterprise holds a SEBI Registered Investment Adviser (RIA) license under SEBI (Investment Advisers) \
Regulations, 2013 — the primary regulatory guideline for the client's advisory vertical.

Classify the assessment text strictly under the SEBI regulatory clauses provided below — these are \
the only SEBI circulars currently active in the enterprise's regulator Library.

Classification Criteria for the enterprise — map every arrangement to exactly ONE of:
financial_outsourcing | it_outsourcing | non_outsourcing | prohibited

An arrangement is OUTSOURCING when a service provider performs, on a
continuing/repetitive basis, a function the enterprise would otherwise undertake itself —
in its capacity as an NBFC (digital arm) or as a SEBI-registered Investment
Adviser (RIA). Key test: (a) it is an activity the enterprise is responsible for, AND
(b) it is ongoing, not a one-off engagement. If it is outsourcing, decide WHICH
kind using the two rules below; if it is not, use non_outsourcing or prohibited.

- financial_outsourcing:
  The provider performs a piece of the client's securities-market / advisory / lending
  business itself — a financial-service function — on a continuing basis, where
  the function is permitted to be outsourced because the final decision stays with
  the client. Examples: KYC processing/support, client onboarding/servicing, data-
  gathering or analytical support that feeds investment advice, fee-collection
  operations, lending / loan onboarding / payment processing. Test: the vendor
  DOES a financial function, it is not merely supplying technology.

- it_outsourcing:
  The provider supplies IT / cloud / SaaS / data-hosting / cybersecurity /
  platform services that the enterprise runs its business on — technology delivery, not a
  financial function. Examples: cloud/SaaS solutions, hosting of the client's data or
  applications, software development, data centre, cybersecurity, platform
  operations, system integration. Classify here even when the technology touches
  sensitive data — hosting/processing data is still IT delivery, not performing a
  financial function.

- non_outsourcing (Exclusions — arrangements outside the outsourcing framework):
    • Statutory / Professional Services: legal counsel, statutory audit, the
      compliance audit by a member of ICAI/ICSI/ICMAI, one-time / advisory
      consultancy engagements.
    • Infrastructure & Utilities: telecom, electricity, water, internet (ISPs).
    • General Support: catering, housekeeping, courier, standardised office
      security.
    • Market Infrastructure: services the enterprise merely USES that are run by the
      market/regulator — stock exchanges (NSE/BSE), clearing corporations (CCIL),
      depositories, KYC Registration Agencies (KRAs), IAASB/RAASB and the
      Centralised Fee Collection Mechanism (CeFCoM), and other recognised MIIs.
    • Off-the-shelf Software: pure licensing of mass-market software with no
      significant customisation and no delegation of a the enterprise function.
  Also non_outsourcing if it is a one-off engagement or not a function the client
  itself performs on a continuing basis.

- prohibited (cannot be outsourced under any circumstance):
    • Management / Control Functions: Compliance, Internal Audit, Risk Management.
    • Advisory Core (SEBI RIA): rendering investment advice and the final
      suitability / investment decision. (Data-gathering or analytical support may
      be outsourced — that is financial_outsourcing — but the decision must remain
      with the client.)
    • KYC Decisioning: KYC processing/support may be outsourced (financial_
      outsourcing), but the final customer onboarding decision must remain with
      the client, consistent with the KRA Regulations.
    • Any activity whose outsourcing would impair the regulator's (SEBI/RBI) or
      auditors' ability to supervise, inspect, or access the client's records.


OUTSOURCING PRINCIPLES :
- Before finalising an outsourcing label, weigh the arrangement against the Principles for \
Outsourcing (Annexure H, clause 13.4): the outsourcing must not create unmanaged operational, \
reputational, legal, concentration or exit-strategy risk, and the enterprise must retain ultimate control \
and accountability for the outsourced activity.
- Per clause 13.5 (Activities that shall NOT be Outsourced), core business activities and \
compliance functions can never be outsourced — label these "prohibited". For an RIA this covers \
the final suitability assessment, the investment-advice decision, and the KYC onboarding decision.

""" + _REASONING_FORMAT + _SEBI_PRINCIPLES_SECTION

# Bump this WHENEVER DEFAULT_GUIDANCE_RBI/SEBI change. The startup sync
# (_seed_prompts_if_needed in app/main.py) compares it to the version stored on
# each DB prompt row and re-writes the row when they differ — so a prompt change
# propagates to every environment automatically on the next deploy, like a
# migration, with no manual reseed. (Treat it like an Alembic revision: change
# the prompt text and the version in the same commit.)
PROMPT_VERSION = "v2"


def _coerce_reasoning(value) -> str:
    """reasoning must be a plain string for storage and for the UI to render.
    A custom agent prompt can make the model emit it as a JSON object (one key
    per section) or a list — flatten those into "Label: text" lines, which the
    reviewer UI already parses back into sections."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return "" if value is None else str(value)


class GeminiLLMAdapter:
    model_version = "gemini-2.5-flash"

    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key)

    async def classify(
        self,
        text: str,
        clauses: list[dict],
        module: str = "M1",
        regulator: str = "RBI",
        system_prompt: str | None = None,
        model_version: str | None = None,
        temperature: float | None = None,
    ) -> ClassificationResult:
        # A classification agent may override the model and temperature; fall back
        # to the reproducible defaults (this class's model, temperature 0) when
        # not supplied. seed and the JSON/thinking config stay fixed regardless.
        model = model_version or self.model_version
        temp = temperature if temperature is not None else 0.0
        # Caller always knows which regulator this call is for (classification_service
        # runs one call per regulator) — don't infer it from clauses[0], which doesn't
        # exist when clauses is empty and would silently mislabel the "no clauses"
        # message with the wrong regulator.
        regulator = regulator.upper()
        # Editable guidance comes from the DB when the gateway supplies it;
        # otherwise fall back to the in-code default for this regulator. The
        # fixed grounding + JSON contract are always appended afterwards.
        guidance = system_prompt or (
            DEFAULT_GUIDANCE_SEBI if regulator == "SEBI" else DEFAULT_GUIDANCE_RBI
        )

        clause_summary = json.dumps(
            [
                {
                    "id": str(c["id"]),
                    "clause_ref": c.get("clause_ref"),
                    "tags": c.get("tags"),
                    # full ingested paragraphs run longer than the old hand-typed
                    # 300-char paraphrase rows did — cap higher so the model
                    # sees the whole paragraph, not a mid-sentence cutoff.
                    "text": (c.get("text") or ""),
                }
                for c in clauses
            ],
            indent=2,
        )

        truncated = len(text) > MAX_CLASSIFY_TEXT_CHARS
        prompt = (
            f"{guidance}\n\n"
            f"{_GROUNDING_RULE}\n\n"
            f"{_FORM_ANSWER_RULE}\n\n"
            f"{_OUTPUT_CONTRACT}\n\n"
            f"{regulator} REGULATORY CLAUSES:\n{clause_summary}\n\n"
            f"ASSESSMENT TEXT:\n{text[:MAX_CLASSIFY_TEXT_CHARS]}\n\n"
            "Return JSON classification:"
        )

        # response_mime_type forces Gemini to emit syntactically valid JSON —
        # without it the model sometimes replies with prose or a truncated
        # object, which fails json.loads and drops us into the fallback
        # (the "unparsable response" default we were seeing).
        #
        # thinking_budget=0 disables Gemini 2.5 Flash's internal "thinking"
        # phase. Those hidden reasoning tokens are drawn from the same output
        # budget as the answer, so with thinking on and a large clause set the
        # model could spend the whole budget thinking and return an empty
        # answer — which is exactly what broke both regulators. Grounded
        # classification against supplied clauses doesn't need extended
        # chain-of-thought, so turning it off is both safer and cheaper.
        #
        # temperature 0 + fixed seed make a given assessment classify
        # reproducibly, which a compliance decision should be.
        config = types.GenerateContentConfig(
            temperature=temp,
            seed=42,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
        )

        raw = (response.text or "").strip()
        # JSON mode should make fences unnecessary, but strip them defensively
        # in case the model still wraps the object.
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Surface WHY it failed so the fallback isn't a black box: an empty
            # raw with finish_reason MAX_TOKENS means the output budget was
            # exhausted; SAFETY means the response was blocked; a non-empty raw
            # means the model genuinely returned malformed JSON.
            finish_reason = None
            try:
                finish_reason = response.candidates[0].finish_reason
            except (AttributeError, IndexError, TypeError):
                pass
            logger.warning(
                "Gemini %s returned unparsable output (finish_reason=%s, len=%d): %s",
                regulator, finish_reason, len(raw), raw[:200],
            )
            return _fallback_result(clauses, text)

        label = data.get("label", "non_outsourcing")
        if label not in _VALID_LABELS:
            label = "non_outsourcing"

        # Never trust a cited clause_id at face value — the model can still
        # hallucinate a citation despite the grounding rule above. Drop any
        # evidence item that doesn't match a clause we actually sent it, so
        # a fabricated reference can never reach the UI looking legitimate.
        valid_ids = {str(c["id"]) for c in clauses}
        raw_evidence = data.get("evidence") or []
        # Keep only citations to clauses we actually sent, and dedupe by
        # clause_id (keeping the first) — the model sometimes lists the same
        # clause more than once, which would otherwise show as three identical
        # pieces of "evidence" in the UI.
        evidence = []
        seen_ids: set[str] = set()
        for e in raw_evidence:
            cid = str(e.get("clause_id"))
            if cid in valid_ids and cid not in seen_ids:
                seen_ids.add(cid)
                evidence.append(e)
        clause_ids = [e["clause_id"] for e in evidence]

        reasoning = _coerce_reasoning(data.get("reasoning", ""))
        confidence = float(data.get("confidence", 0.75))
        if not clauses:
            reasoning = (
                f"No active {regulator} regulator documents are currently in the Library — "
                "this label is a default, not a grounded regulatory citation. Add official "
                "regulator documents to the Library to enable citation-backed classification."
            )
            confidence = 0.0
        elif raw_evidence and not evidence:
            # The model cited something, but every citation failed
            # validation — it invented a reference not present in what we
            # gave it. Surface that plainly rather than silently dropping it.
            reasoning = (
                f"{reasoning} (The regulation referenced above could not be verified against "
                "the Library's active clauses and has been withheld — treat this classification "
                "as ungrounded.)"
            ).strip()
            confidence = min(confidence, 0.2)

        prompt_tokens, completion_tokens, total_tokens = _usage_tokens(response)
        return ClassificationResult(
            label=label,
            confidence=confidence,
            evidence=evidence,
            clause_ids=clause_ids,
            model_version=model,
            reasoning=reasoning,
            truncated=truncated,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def score_suggest(self, intake: dict) -> dict:
        return {"emphasis_factors": list(intake.keys())[:3], "model_version": self.model_version}


def _usage_tokens(response) -> tuple[int | None, int | None, int | None]:
    """Pull (prompt, completion, total) token counts off a google-genai response.

    Returns Nones when the SDK didn't attach usage_metadata, so callers can log
    "unknown" rather than a misleading zero.
    """
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None, None
    return (
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "total_token_count", None),
    )


def _fallback_result(clauses: list[dict], text: str) -> ClassificationResult:
    first = clauses[0] if clauses else {}
    evidence = (
        [{"clause_id": str(first["id"]), "clause_ref": first.get("clause_ref"), "doc_span": {"start": 0, "end": min(100, len(text))}}]
        if first else []
    )
    return ClassificationResult(
        label="non_outsourcing",
        confidence=0.0,
        evidence=evidence,
        clause_ids=[str(first["id"])] if first else [],
        model_version="gemini-2.5-flash",
        reasoning="Gemini returned an unparsable response; defaulted to non_outsourcing.",
    )
