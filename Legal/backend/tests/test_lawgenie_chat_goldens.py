"""Chat-mode golden shapes (no live LLM).

Run with the rest of the unit suite. Full retrieval eval remains behind
``RUN_RAG_EVAL=1`` in ``tests/eval/``.
"""

from __future__ import annotations

GOLDEN_MODES = {
    "review": {
        "must_mention_tools": ["search_jfpsl_knowledge"],
        "forbid_open_web_first": True,
    },
    "research": {
        "must_mention_tools": ["search_regulatory_knowledge", "web_search"],
        "forbid_open_web_first": False,
    },
    "draft": {
        "must_mention_tools": ["search_jfpsl_knowledge", "[[PLACEHOLDER:"],
        "forbid_open_web_first": True,
    },
}


def test_golden_mode_directives_shape():
    from app.orchestrator.pipeline import _MODE_DIRECTIVES

    for mode, rules in GOLDEN_MODES.items():
        text = _MODE_DIRECTIVES[mode]
        for needle in rules["must_mention_tools"]:
            assert needle in text, f"{mode} missing {needle}"
