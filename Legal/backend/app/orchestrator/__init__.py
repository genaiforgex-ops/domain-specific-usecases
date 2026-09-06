"""LegalOS orchestrator — chat SSE + discrete task agents.

Layering:
  - Chat: ``api/chat.py`` → ``pipeline`` → conversational sub-agents
  - Tasks: API/services → ``tasks`` (rule-based ``rules.classify`` → agent)
  - Shared: ``tools/``, ``guardrails/``, ``prompts/``, ``task_runner``

All environment configuration is read from ``app.config.settings`` only.
"""

from app.orchestrator import tasks as tasks  # noqa: F401 — public task API
