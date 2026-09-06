"""Orchestrator configuration — a thin, typed view over ``app.config.settings``.

Per the engineering conventions, ``app/config.py`` is the ONLY module that reads
the environment. This module simply surfaces the orchestrator-relevant values as
plain module-level constants so the rest of ``app/orchestrator/`` can import them
without reaching back into the global settings object everywhere.
"""

from __future__ import annotations

from app.config import settings

APP_NAME: str = settings.orch_app_name
SESSION_DSN: str = settings.orch_session_dsn

COMPACTION_ENABLED: bool = settings.orch_compaction_enabled
COMPACTION_INTERVAL_TURNS: int = settings.orch_compaction_interval_turns
COMPACTION_OVERLAP_TURNS: int = settings.orch_compaction_overlap_turns
HISTORY_TURNS_FOR_CONTEXT: int = settings.orch_history_turns_for_context

ARTIFACT_BACKEND: str = settings.orch_artifact_backend
SESSION_BUCKET: str = settings.orch_session_bucket

PII_MASKING_ENABLED: bool = settings.orch_pii_masking_enabled
DLP_ENABLED: bool = settings.orch_dlp_enabled
ARMOR_ENABLED: bool = settings.orch_armor_enabled
MAX_CONTEXT_CHARS: int = settings.orch_max_context_chars

WEB_SEARCH_ENABLED: bool = settings.orch_web_search_enabled
WEB_SEARCH_MAX_RESULTS: int = settings.orch_web_search_max_results
GOOGLE_CSE_API_KEY: str = settings.google_cse_api_key
GOOGLE_CSE_ID: str = settings.google_cse_id

JFPSL_RAG_ENABLED: bool = settings.orch_jfpsl_rag_enabled
JFPSL_RAG_MAX_RESULTS: int = settings.orch_jfpsl_rag_max_results
VERTEX_RAG_CORPUS_RESOURCE: str = settings.vertex_rag_corpus_resource
VERTEX_RAG_LOCATION: str = settings.vertex_rag_location

REGULATORY_RAG_ENABLED: bool = settings.regulatory_rag_enabled
REGULATORY_RAG_MAX_RESULTS: int = settings.regulatory_rag_max_results

RESEARCH_FANOUT_ENABLED: bool = settings.orch_research_fanout_enabled
RESEARCH_LANE_TIMEOUT_SECONDS: int = settings.orch_research_lane_timeout_seconds
RESEARCH_VERIFY_ENABLED: bool = settings.orch_research_verify_enabled
