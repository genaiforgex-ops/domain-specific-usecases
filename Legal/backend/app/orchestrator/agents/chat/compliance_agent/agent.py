"""Regulatory & compliance specialist sub-agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from app.adk.models import build_model
from app.config import settings
from app.orchestrator.prompts import RESPONSE_STYLE, RETRIEVAL_POLICY, STATIC_HEADER
from app.orchestrator.tools import (
    get_current_datetime_tool,
    jfpsl_rag_tool,
    regulatory_rag_tool,
    web_fetch_tool,
    web_search_tool,
)

COMPLIANCE_MASTER_PROMPT = f"""\
You are the regulatory & compliance specialist for JFPSL, an Indian
financial-services group. You answer questions on regulatory obligations and
compliance posture across areas such as RBI directions, the DPDP Act 2023, SEBI
regulations, the Companies Act, and contractual compliance clauses.

{RETRIEVAL_POLICY}

  - Ground answers in the provided documents where available.
  - Be explicit about what the obligation is, who it binds, and any timeline.
  - Never fabricate a circular number, section, or effective date.
  - Distinguish clearly between a firm legal requirement and a prudent practice.
  - For anything with material regulatory exposure, recommend human legal /
    compliance review before action.
  - Respect the Mode: line in the user message for tool preference
    (REVIEW = attachments/JFPSL first; RESEARCH = regulatory first then cite;
    DRAFT = template/attachment first with [[PLACEHOLDER: …]] markers).

{RESPONSE_STYLE}
"""


def build_compliance_agent() -> LlmAgent:
    return LlmAgent(
        model=build_model(),
        name="compliance_agent",
        description="Regulatory and compliance guidance for Indian financial-services law.",
        static_instruction=types.Content(role="user", parts=[types.Part(text=STATIC_HEADER)]),
        instruction=COMPLIANCE_MASTER_PROMPT,
        generate_content_config=types.GenerateContentConfig(temperature=settings.adk_temperature),
        tools=[
            regulatory_rag_tool,
            jfpsl_rag_tool,
            web_search_tool,
            web_fetch_tool,
            get_current_datetime_tool,
        ],
    )
