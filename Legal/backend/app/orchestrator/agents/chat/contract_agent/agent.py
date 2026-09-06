"""Contract & clause specialist sub-agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from app.adk.models import build_model
from app.config import settings
from app.orchestrator.prompts import RESPONSE_STYLE, RETRIEVAL_POLICY, STATIC_HEADER
from app.orchestrator.tools import (
    get_current_datetime_tool,
    get_msa_document_tool,
    jfpsl_rag_tool,
    regulatory_rag_tool,
    web_fetch_tool,
    web_search_tool,
)

CONTRACT_MASTER_PROMPT = f"""\
You are the contract specialist. You analyse contracts, MSAs, NDAs, and
individual clauses for JFPSL in-house counsel.

{RETRIEVAL_POLICY}

When a document IS provided in the context block, ground everything in it:
  - Identify the material clauses (liability, indemnity, payment, termination,
    confidentiality, data protection, governing law, IP).
  - Flag risks as high / medium / low with a one-line rationale each, always
    against JFPSL's interest as the reviewing party.
  - Quote the exact clause text you are flagging.
  - Note missing clauses the standard position would require.
  - Suggest concrete redline language when asked.

Be precise and conservative. Never invent clause numbers or terms that are not
in the document or RAG results. Recommend human legal review for high-risk items.
Respect the Mode: line in the user message for tool preference
(REVIEW = attachments/JFPSL first, web only if corpora empty;
RESEARCH = regulatory first then cite; DRAFT = template/attachment first,
deliver full draft with [[PLACEHOLDER: …]] markers and a short placeholders list).

{RESPONSE_STYLE}
"""


def build_contract_agent() -> LlmAgent:
    return LlmAgent(
        model=build_model(),
        name="contract_agent",
        description="Contract, clause, MSA/NDA analysis, negotiation and redline drafting.",
        static_instruction=types.Content(role="user", parts=[types.Part(text=STATIC_HEADER)]),
        instruction=CONTRACT_MASTER_PROMPT,
        generate_content_config=types.GenerateContentConfig(temperature=settings.adk_temperature),
        tools=[
            jfpsl_rag_tool,
            regulatory_rag_tool,
            web_search_tool,
            web_fetch_tool,
            get_msa_document_tool,
            get_current_datetime_tool,
        ],
    )
