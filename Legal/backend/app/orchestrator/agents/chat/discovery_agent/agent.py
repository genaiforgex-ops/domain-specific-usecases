"""General legal Q&A / knowledge-base fallback sub-agent.

Catch-all for cross-topic and general legal questions. Uses Vertex AI RAG Engine
(``search_jfpsl_knowledge``) over the JFPSL legal-templates corpus.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from app.adk.models import build_model
from app.config import settings
from app.orchestrator.prompts import RESPONSE_STYLE, RETRIEVAL_POLICY, STATIC_HEADER
from app.orchestrator.tools import (
    get_current_datetime_tool,
    get_gmail_thread_tool,
    jfpsl_rag_tool,
    regulatory_rag_tool,
    web_fetch_tool,
    web_search_tool,
)

DISCOVERY_MASTER_PROMPT = f"""\
You are the general legal assistant. You handle broad or cross-topic legal
questions, definitions, and knowledge-base lookups for JFPSL.

{RETRIEVAL_POLICY}

  - Answer from the conversation history, any attached documents, and the tools
    available to you. Do not invent authorities or facts.
  - If a question clearly belongs to contracts or compliance, give a useful
    general answer and note that a deeper review is available.
  - When you genuinely do not have the information, say so plainly and suggest
    where the user could find it inside LegalOS.
  - Keep answers focused and cite the source you relied on.
  - Respect the Mode: line in the user message for tool preference
    (REVIEW = attachments/JFPSL first; RESEARCH = regulatory first then cite;
    DRAFT = template/attachment first with [[PLACEHOLDER: …]] markers).

{RESPONSE_STYLE}
"""


def build_discovery_agent() -> LlmAgent:
    return LlmAgent(
        model=build_model(),
        name="discovery_agent",
        description="General legal Q&A, definitions, and knowledge-base grounded answers.",
        static_instruction=types.Content(role="user", parts=[types.Part(text=STATIC_HEADER)]),
        instruction=DISCOVERY_MASTER_PROMPT,
        generate_content_config=types.GenerateContentConfig(temperature=settings.adk_temperature),
        tools=[
            jfpsl_rag_tool,
            regulatory_rag_tool,
            web_search_tool,
            web_fetch_tool,
            get_gmail_thread_tool,
            get_current_datetime_tool,
        ],
    )
