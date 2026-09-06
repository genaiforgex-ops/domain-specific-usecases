"""Prompt modules for the orchestrator (behavior as data).

Each concern lives in its own file. Assemble the root instruction with
`build_root_instruction()`; sub-agents import the pieces they need.
"""

from app.orchestrator.prompts.conversation_flow import CONVERSATION_FLOW
from app.orchestrator.prompts.loaders import load_jfpsl_template_standards
from app.orchestrator.prompts.persona_and_mission import PERSONA_AND_MISSION
from app.orchestrator.prompts.response_style import RESPONSE_STYLE
from app.orchestrator.prompts.retrieval_policy import RETRIEVAL_POLICY
from app.orchestrator.prompts.review_context import build_review_context, format_playbook
from app.orchestrator.prompts.routing_policy import ROUTING_POLICY
from app.orchestrator.prompts.safety_compliance_and_guardrails import SAFETY_AND_GUARDRAILS
from app.orchestrator.prompts.static_header import STATIC_HEADER


def build_root_instruction() -> str:
    return "\n\n".join(
        [
            PERSONA_AND_MISSION,
            RETRIEVAL_POLICY,
            ROUTING_POLICY,
            CONVERSATION_FLOW,
            SAFETY_AND_GUARDRAILS,
            RESPONSE_STYLE,
        ]
    )


__all__ = [
    "PERSONA_AND_MISSION",
    "RETRIEVAL_POLICY",
    "ROUTING_POLICY",
    "CONVERSATION_FLOW",
    "SAFETY_AND_GUARDRAILS",
    "RESPONSE_STYLE",
    "STATIC_HEADER",
    "build_root_instruction",
    "build_review_context",
    "format_playbook",
    "load_jfpsl_template_standards",
]
