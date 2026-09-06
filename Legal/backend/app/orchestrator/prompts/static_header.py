"""Immutable org context — supplied as the agent's `static_instruction`."""

from app.orchestrator.prompts.loaders import load_jfpsl_template_standards

_BASE_HEADER = """\
You are the LegalOS Assistant, the conversational legal AI for JFPSL (Jio Finance
Platform and Services Ltd) Corporate Legal. You operate strictly inside LegalOS,
an internal, RBAC-governed platform. You serve in-house legal counsel, legal
operations, and authorized business users. You are not a substitute for a
qualified lawyer and your output is decision-support, never final legal advice.
"""


def build_static_header() -> str:
    standards = load_jfpsl_template_standards(max_chars=6000)
    return (
        f"{_BASE_HEADER}\n\n"
        "# JFPSL Template Standards (distilled reference)\n"
        "Use search_jfpsl_knowledge for live corpus retrieval; this block is a "
        "compact summary of approved JFPSL template language.\n\n"
        f"{standards}"
    )


STATIC_HEADER = build_static_header()
