"""AgentId → ADK builder. Rule-based selection lives in ``rules.classify``."""

from __future__ import annotations

from collections.abc import Callable

from google.adk.agents import LlmAgent

from app.orchestrator.agents import (
    build_change_summary_agent,
    build_docx_edit_agent,
    build_edit_agent,
    build_email_reply_agent,
    build_email_task_agent,
    build_legal_qa_agent,
    build_news_analysis_agent,
    build_research_agent,
    build_review_agent,
)
from app.orchestrator.rules import AgentId

Builder = Callable[[], LlmAgent]

_BUILDERS: dict[AgentId, Builder] = {
    AgentId.MSA_REVIEW: build_review_agent,
    AgentId.CONTRACT_REVIEW: build_review_agent,
    AgentId.MSA_EDIT: build_docx_edit_agent,  # preferred; edit_document uses build_edit_agent
    AgentId.MSA_CHANGE_SUMMARY: build_change_summary_agent,
    AgentId.GMAIL_REPLY: build_email_reply_agent,
    AgentId.EMAIL_TASKS: build_email_task_agent,
    AgentId.LEGAL_QA: build_legal_qa_agent,
    AgentId.RESEARCH: build_research_agent,
    AgentId.NEWS_ANALYSIS: build_news_analysis_agent,
}


def get_builder(agent_id: AgentId) -> Builder:
    try:
        return _BUILDERS[agent_id]
    except KeyError as exc:
        raise KeyError(f"No builder registered for agent_id={agent_id}") from exc


def build_agent(agent_id: AgentId) -> LlmAgent:
    return get_builder(agent_id)()
