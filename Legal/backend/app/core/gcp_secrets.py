"""Load secrets from Google Cloud Secret Manager."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


def _on_cloud_run() -> bool:
    """True when running on Cloud Run / GCP compute (use ADC, not a key file)."""
    return bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))


def _build_client(credentials_file: str = ""):
    """Build a Secret Manager client.

    Off-GCP (local dev) we authenticate with an explicit service-account key
    file when one is configured/exists; otherwise (and always on Cloud Run /
    GKE) we fall back to Application Default Credentials / Workload Identity.
    """
    from google.cloud import secretmanager

    if credentials_file and not _on_cloud_run() and os.path.isfile(credentials_file):
        logger.info("Using service-account key file for Secret Manager: %s", credentials_file)
        return secretmanager.SecretManagerServiceClient.from_service_account_file(
            credentials_file
        )
    return secretmanager.SecretManagerServiceClient()


@lru_cache(maxsize=8)
def get_secret_value(
    project_id: str,
    secret_id: str,
    version: str = "latest",
    credentials_file: str = "",
) -> str:
    """Return the UTF-8 payload of a Secret Manager secret version."""
    client = _build_client(credentials_file)
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def resolve_gcp_project_id(explicit_project_id: str, credentials_file: str = "") -> str:
    if explicit_project_id:
        return explicit_project_id
    try:
        import google.auth
        from google.oauth2 import service_account

        if credentials_file and not _on_cloud_run() and os.path.isfile(credentials_file):
            creds = service_account.Credentials.from_service_account_file(credentials_file)
            return getattr(creds, "project_id", "") or ""
        _, project_id = google.auth.default()
        return project_id or ""
    except Exception:
        return ""


def load_secret_text(project_id: str, secret_id: str, credentials_file: str = "") -> str:
    """Fetch a Secret Manager secret whose payload IS the value (not a JSON blob).

    Used for dedicated single-value secrets (e.g. SMTP username/password secrets).
    Returns "" on any failure so the caller can fall back.
    """
    if not secret_id:
        return ""
    resolved_project = resolve_gcp_project_id(project_id, credentials_file)
    if not resolved_project:
        return ""
    try:
        payload = get_secret_value(resolved_project, secret_id, credentials_file=credentials_file)
    except Exception as exc:
        logger.warning("Failed to load secret %s from Secret Manager: %s", secret_id, exc)
        return ""
    value = (payload or "").strip()
    if value:
        logger.info("Loaded secret %s from Secret Manager", secret_id)
    return value


@lru_cache(maxsize=8)
def load_app_secret_dict(
    project_id: str,
    secret_id: str,
    credentials_file: str = "",
) -> dict[str, Any]:
    """Load the env-scoped app secret JSON blob once (cached).

    Expected shape: flat dict of UPPER_SNAKE keys (DATABASE_URL, JWT_SECRET, …).
    Returns {} on any failure so callers keep env / empty defaults.
    """
    if not secret_id:
        return {}
    resolved_project = resolve_gcp_project_id(project_id, credentials_file)
    if not resolved_project:
        logger.warning(
            "GCP project id could not be resolved; skipping Secret Manager lookup for %s",
            secret_id,
        )
        return {}
    try:
        payload = get_secret_value(resolved_project, secret_id, credentials_file=credentials_file)
    except Exception as exc:
        logger.warning(
            "Failed to load app secret %s from Secret Manager (project=%s): %s",
            secret_id,
            resolved_project,
            exc,
        )
        return {}
    try:
        data = json.loads((payload or "").strip() or "{}")
    except json.JSONDecodeError:
        logger.warning("App secret %s is not valid JSON", secret_id)
        return {}
    if not isinstance(data, dict):
        logger.warning("App secret %s JSON root must be an object", secret_id)
        return {}
    logger.info(
        "Loaded app secret JSON from Secret Manager (project=%s secret=%s keys=%d)",
        resolved_project,
        secret_id,
        len(data),
    )
    return data


def load_app_secret_field(
    project_id: str,
    secret_id: str,
    *field_keys: str,
    credentials_file: str = "",
) -> str:
    """Load one string field from the shared env-scoped app secret JSON blob."""
    if not field_keys:
        return ""
    data = load_app_secret_dict(project_id, secret_id, credentials_file)
    for key in field_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
    return ""


# --- Backward-compatible helpers (thin wrappers over the shared JSON blob) ---


def extract_gemini_api_key(secret_payload: str) -> str:
    """Parse a Secret Manager payload as JSON or a raw API key string."""
    payload = secret_payload.strip()
    if not payload:
        return ""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if not isinstance(data, dict):
        return payload
    for key in ("GEMINI_API_KEY", "gemini_api_key", "GOOGLE_API_KEY", "google_api_key"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_gemini_api_key_from_secret_manager(
    project_id: str,
    secret_id: str,
    credentials_file: str = "",
) -> str:
    return load_app_secret_field(
        project_id,
        secret_id,
        "GEMINI_API_KEY",
        "gemini_api_key",
        "GOOGLE_API_KEY",
        "google_api_key",
        credentials_file=credentials_file,
    )


def load_vertex_rag_from_secret_manager(
    project_id: str,
    secret_id: str,
    credentials_file: str = "",
) -> tuple[str, str]:
    """Load Vertex RAG corpus config from the shared app secret JSON blob."""
    corpus_id = load_app_secret_field(
        project_id,
        secret_id,
        "VERTEX_RAG_CORPUS_ID",
        "vertex_rag_corpus_id",
        credentials_file=credentials_file,
    )
    location = load_app_secret_field(
        project_id,
        secret_id,
        "VERTEX_RAG_LOCATION",
        "vertex_rag_location",
        credentials_file=credentials_file,
    )
    return corpus_id, location
