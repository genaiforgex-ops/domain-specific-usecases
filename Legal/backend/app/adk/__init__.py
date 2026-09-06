"""Low-level Google ADK helpers used by the orchestrator.

Layout:
    models.py   build_model() — provider-agnostic ADK model (Gemini or on-prem).
    runner.py   sync bridge (``_run_coro``) for single-turn agent calls.

All LegalAI generation lives under ``app.orchestrator`` (task_runner + chat pipeline).
"""
