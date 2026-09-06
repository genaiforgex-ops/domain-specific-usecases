"""Rule-based agent dispatch — never an LLM.

API routes already know the product surface (module) and the operation.
``classify(module, operation)`` maps that pair to a fixed ``AgentId``.
"""

from __future__ import annotations

from enum import StrEnum


class AgentId(StrEnum):
    MSA_REVIEW = "msa_review"
    MSA_EDIT = "msa_edit"
    MSA_CHANGE_SUMMARY = "msa_change_summary"
    CONTRACT_REVIEW = "contract_review"
    GMAIL_REPLY = "gmail_reply"
    EMAIL_TASKS = "email_tasks"
    LEGAL_QA = "legal_qa"
    RESEARCH = "research"
    NEWS_ANALYSIS = "news_analysis"
    # Chat specialists (conversational; not selected via this classifier)
    CHAT_CONTRACT = "contract_agent"
    CHAT_COMPLIANCE = "compliance_agent"
    CHAT_DISCOVERY = "discovery_agent"


# (module, operation) → agent. Unknown pairs raise KeyError so miswiring is loud.
_RULES: dict[tuple[str, str], AgentId] = {
    ("msa_automation", "review_contract"): AgentId.MSA_REVIEW,
    ("msa_automation", "vendor_review"): AgentId.MSA_REVIEW,
    ("msa_automation", "prompt_edit"): AgentId.MSA_EDIT,
    ("msa_automation", "compare_documents"): AgentId.MSA_CHANGE_SUMMARY,
    ("contract_review", "review_contract"): AgentId.CONTRACT_REVIEW,
    ("contract_review", "prompt_edit"): AgentId.MSA_EDIT,  # same edit agent
    ("gmail", "generate_reply"): AgentId.GMAIL_REPLY,
    ("gmail", "regenerate_reply"): AgentId.GMAIL_REPLY,
    ("gmail", "autodraft_reply"): AgentId.GMAIL_REPLY,
    ("tasks", "extract_from_email"): AgentId.EMAIL_TASKS,
    ("legal_bot", "answer_query"): AgentId.LEGAL_QA,
    ("legal_research", "generate_research_note"): AgentId.RESEARCH,
    ("legal_news", "analyse_regulatory_update"): AgentId.NEWS_ANALYSIS,
    ("legal_news", "save_discovered"): AgentId.NEWS_ANALYSIS,
}


def classify(module: str, operation: str) -> AgentId:
    """Return the agent for a known module+operation. Raises KeyError if unknown."""
    key = (module.strip().lower(), operation.strip().lower())
    try:
        return _RULES[key]
    except KeyError as exc:
        raise KeyError(
            f"No rule for module={module!r} operation={operation!r}. "
            "Add it to orchestrator.rules._RULES (rule-based only — no LLM router)."
        ) from exc
