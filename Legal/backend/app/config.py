"""Application settings.

Priority (Infosec):
  1. Process environment / ``.env`` (explicit override)
  2. Env-scoped GCP Secret Manager JSON (``legalos_dev`` / ``legalos_uat`` / ``legalos_prod``)
  3. Empty / non-secret structural defaults only — never hard-code credentials,
     API keys, JWT secrets, DB URLs, OAuth secrets, or environment hostnames.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.gcp_secrets import (
    load_app_secret_dict,
    load_secret_text,
    resolve_gcp_project_id,
)

logger = logging.getLogger(__name__)

# backend/app/config.py → backend root. In Docker the backend is mounted at /app
# (so parents[1] == /app). In the monorepo, parents[1] == …/backend and the
# repo root is one level up (has frontend/).
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = (
    _BACKEND_ROOT.parent
    if (_BACKEND_ROOT.parent / "frontend").is_dir()
    else _BACKEND_ROOT
)
# Resolve the .env path absolutely so it loads regardless of the working
# directory (uvicorn from backend/, alembic from backend/, docker, etc.).
_ENV_FILE = _REPO_ROOT / ".env"
if not _ENV_FILE.is_file():
    _ENV_FILE = _BACKEND_ROOT / ".env"

# GCP Secret Manager app-secret id per deployment environment (name only — not a secret).
_GCP_SECRET_BY_ENV: dict[str, str] = {
    "dev": "legalos_dev",
    "uat": "legalos_uat",
    "prod": "legalos_prod",
    "production": "legalos_prod",
    "preprod": "legalos_uat",
}

# Environments where Keycloak / Jio SSO is active (LEGALOS_ENV, lowercased).
# To enable SSO in a new environment, add its LEGALOS_ENV value here.
_KEYCLOAK_SSO_ENVS: frozenset[str] = frozenset({"dev", "uat"})

# IAM backend URL key in Secret Manager. UAT uses a distinct key so DEV
# (IAM_BACKEND_URL in legalos_dev) is never read from the UAT blob.
_IAM_BACKEND_URL_KEY_BY_ENV: dict[str, str] = {
    "uat": "UAT_IAM_BACKEND_URL",
}

# Keycloak SSO keys in Secret Manager, per LEGALOS_ENV.
_KEYCLOAK_SSO_KEYS_BY_ENV: dict[str, tuple[tuple[str, str], ...]] = {
    "dev": (
        ("DEV_KEYCLOAK_URL", "keycloak_url"),
        ("DEV_KEYCLOAK_REALM", "keycloak_realm"),
        ("KEYCLOAK_IDP_HINT", "keycloak_idp_hint"),
    ),
    "uat": (
        ("UAT_KEYCLOAK_URL", "keycloak_url"),
        ("UAT_KEYCLOAK_REALM", "keycloak_realm"),
        ("UAT_KEYCLOAK_IDP_HINT", "keycloak_idp_hint"),
    ),
}

# Public Keycloak client id when the env-scoped JSON blob does not set it.
# DEV already stores KEYCLOAK_CLIENT_ID in legalos_dev — do not override it.
_KEYCLOAK_CLIENT_ID_BY_ENV: dict[str, str] = {
    "uat": "legalos-uat",
}

# Secret Manager JSON key → Settings attribute.
# Env vars with the same UPPER name always win (checked via os.environ).
_APP_SECRET_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("DATABASE_URL", "database_url"),
    ("JWT_SECRET", "jwt_secret"),
    ("CORS_ORIGINS", "cors_origins"),
    ("GCP_PROJECT_ID", "gcp_project_id"),
    ("GEMINI_API_KEY", "gemini_api_key"),
    ("GEMINI_MODEL", "gemini_model"),
    ("AI_BACKEND", "ai_backend"),
    ("ADK_MODEL", "adk_model"),
    ("ADK_LITELLM_API_BASE", "adk_litellm_api_base"),
    ("ADK_LITELLM_API_KEY", "adk_litellm_api_key"),
    ("NOTIFICATIONS_ENABLED", "notifications_enabled"),
    ("FRONTEND_BASE_URL", "frontend_base_url"),
    ("SMTP_HOST", "smtp_host"),
    ("SMTP_PORT", "smtp_port"),
    ("SMTP_USE_TLS", "smtp_use_tls"),
    ("SMTP_FROM_NAME", "smtp_from_name"),
    ("SMTP_USERNAME", "smtp_username"),
    ("SMTP_PASSWORD", "smtp_password"),
    ("SMTP_USERNAME_SECRET_NAME", "smtp_username_secret_name"),
    ("SMTP_PASSWORD_SECRET_NAME", "smtp_password_secret_name"),
    ("GMAIL_CLIENT_ID", "gmail_client_id"),
    ("GMAIL_CLIENT_SECRET", "gmail_client_secret"),
    ("GMAIL_REDIRECT_URI", "gmail_redirect_uri"),
    ("GMAIL_ENABLED", "gmail_enabled"),
    ("GMAIL_LABEL", "gmail_label"),
    ("GMAIL_POLL_INTERVAL_SECONDS", "gmail_poll_interval_seconds"),
    ("ONLYOFFICE_ENABLED", "onlyoffice_enabled"),
    ("ONLYOFFICE_JWT_SECRET", "onlyoffice_jwt_secret"),
    ("ONLYOFFICE_PUBLIC_URL", "onlyoffice_public_url"),
    ("ONLYOFFICE_DOCUMENT_BASE_URL", "onlyoffice_document_base_url"),
    ("ONLYOFFICE_CALLBACK_BASE_URL", "onlyoffice_callback_base_url"),
    ("ONLYOFFICE_COMMAND_BASE_URL", "onlyoffice_command_base_url"),
    ("ORCH_JFPSL_RAG_ENABLED", "orch_jfpsl_rag_enabled"),
    ("ORCH_JFPSL_RAG_MAX_RESULTS", "orch_jfpsl_rag_max_results"),
    ("VERTEX_RAG_CORPUS_ID", "vertex_rag_corpus_id"),
    ("VERTEX_RAG_LOCATION", "vertex_rag_location"),
    ("REGULATORY_VERTEX_CORPUS_ID", "regulatory_vertex_corpus_id"),
    ("ORCH_WEB_SEARCH_ENABLED", "orch_web_search_enabled"),
    ("SEED_DEFAULT_PASSWORD", "seed_default_password"),
    ("GOOGLE_CSE_API_KEY", "google_cse_api_key"),
    ("GOOGLE_CSE_ID", "google_cse_id"),
    ("LEGAL_TEMPLATES_BUCKET", "legal_templates_bucket"),
    ("LEGAL_TEMPLATES_PREFIX", "legal_templates_prefix"),
    ("LEGAL_CONTRACTS_PREFIX", "legal_contracts_prefix"),
    ("DOCUMENT_STORAGE_BACKEND", "document_storage_backend"),
    ("MSA_DOCUMENTS_PREFIX", "msa_documents_prefix"),
    ("LOCAL_STORAGE_PATH", "local_storage_path"),
    # ── Central IAM user sync (always from Secret Manager — not .env) ──
    # IAM_BACKEND_URL is remapped per env in _hydrate_from_secret_manager.
    ("IAM_BACKEND_URL", "iam_backend_url"),
    ("IAM_CLIENT_SECRET", "iam_client_secret"),
    ("KEYCLOAK_CLIENT_ID", "keycloak_client_id"),
    ("IAM_SYNC_INTERVAL_SECONDS", "iam_sync_interval_seconds"),
)

# Legacy keys in older secret blobs where the value IS the credential.
_APP_SECRET_ALIASES: tuple[tuple[str, str], ...] = (
    ("SMTP_USERNAME_SECRET", "smtp_username"),
    ("SMTP_PASSWORD_SECRET", "smtp_password"),
)


def _env_provided(secret_key: str) -> bool:
    """True when the process environment explicitly sets this key."""
    return secret_key in os.environ and str(os.environ.get(secret_key, "")).strip() != ""


def _is_placeholder_secret(value: str) -> bool:
    """True for unset/template secret values from example JSON blobs."""
    normalized = value.strip().lower().replace("_", "-")
    return not normalized or normalized in {"replace-me", "changeme", "change-me", "todo"}


def _coerce(value: Any, current: Any) -> Any:
    """Coerce a secret JSON value to the type of the current settings field."""
    if value is None:
        return current
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return str(value).strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    # --- Secrets / env-specific values: empty defaults; hydrate from SM ---
    database_url: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    access_token_absolute_hours: int = 12

    ai_backend: str = "stub"
    model_version: str = "legalos-stub-0.1"

    # LEGALOS_ENV selects which app secret to load (dev/uat/prod). Not a secret.
    legalos_env: str = "dev"
    gcp_project_id: str = ""
    gcp_secret_name: str = ""
    # Optional local SA key path (from env GCP_SERVICE_ACCOUNT_FILE only).
    # On GKE use Workload Identity / ADC — do not bake a key path into code.
    gcp_service_account_file: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    gemini_max_clauses_per_call: int = 25

    adk_model: str = "gemini-2.5-flash"
    adk_temperature: float = 0.2
    adk_max_clauses_per_call: int = 25
    adk_litellm_api_base: str = ""
    adk_litellm_api_key: str = ""

    notifications_enabled: bool = False
    notification_dispatch_interval_seconds: int = 30
    notification_max_attempts: int = 5
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_from_name: str = "LegalOS Notifications"
    smtp_password: str = ""
    # Names of dedicated SM secrets (optional). Never hard-code env-specific ids.
    smtp_username_secret_name: str = ""
    smtp_password_secret_name: str = ""
    frontend_base_url: str = ""

    invite_token_expire_hours: int = 168
    seed_default_password: str = ""

    news_scrape_enabled: bool = False
    news_scrape_interval_seconds: int = 3600

    cors_origins: str = ""

    local_storage_path: str = "/tmp/legalos-storage"
    max_upload_bytes: int = 25 * 1024 * 1024

    # MSA negotiation blobs. Prefer DOCUMENT_STORAGE_BACKEND=gcs in Secret Manager
    # so uploads / OnlyOffice saves survive pod/volume deletion.
    # Objects land at gs://{legal_templates_bucket}/{msa_documents_prefix}/…
    document_storage_backend: str = "local"
    # MSA uploads / OnlyOffice saves → gs://{bucket}/{msa_documents_prefix}/…
    msa_documents_prefix: str = "legal_live_docs"

    legal_templates_bucket: str = ""
    legal_templates_prefix: str = "legal_templates"
    legal_contracts_prefix: str = "contracts"

    onlyoffice_enabled: bool = False
    onlyoffice_jwt_secret: str = ""
    onlyoffice_public_url: str = ""
    onlyoffice_document_base_url: str = ""
    onlyoffice_callback_base_url: str = ""
    onlyoffice_command_base_url: str = ""
    onlyoffice_command_path: str = ""
    onlyoffice_force_track_changes: bool = True

    orch_enabled: bool = True
    orch_app_name: str = "legalos_orchestrator"
    orch_session_db_url: str = ""
    orch_compaction_enabled: bool = False
    orch_compaction_interval_turns: int = 10
    orch_compaction_overlap_turns: int = 2
    orch_history_turns_for_context: int = 6
    orch_artifact_backend: str = "memory"
    orch_session_bucket: str = ""
    orch_pii_masking_enabled: bool = True
    orch_dlp_enabled: bool = False
    orch_armor_enabled: bool = True
    orch_max_context_chars: int = 50000
    orch_web_search_enabled: bool = True
    orch_web_search_max_results: int = 5
    google_cse_api_key: str = ""
    google_cse_id: str = ""
    orch_jfpsl_rag_enabled: bool = True
    orch_jfpsl_rag_max_results: int = 5
    vertex_rag_corpus_id: str = ""
    vertex_rag_location: str = ""

    # ── Regulatory knowledge corpus (statutes / master directions / circulars) ──
    # Postgres owns the clause chunks, labels and supersession; the optional Vertex
    # corpus below only adds a second doc-level recall channel.
    regulatory_rag_enabled: bool = True
    regulatory_rag_max_results: int = 8
    regulatory_vertex_corpus_id: str = ""
    regulatory_vertex_sync_enabled: bool = False
    regulatory_embed_model: str = "gemini-embedding-001"
    regulatory_embed_dims: int = 768
    regulatory_embed_batch: int = 100
    regulatory_refresh_enabled: bool = False
    regulatory_refresh_interval_seconds: int = 86400
    orch_research_fanout_enabled: bool = False
    orch_research_lane_timeout_seconds: int = 20
    orch_research_verify_enabled: bool = False

    templates_dir: str = str(_REPO_ROOT / "Templates")
    contracts_dir: str = str(_REPO_ROOT / "contracts")
    rag_upload_state_file: str = str(_BACKEND_ROOT / "config" / ".rag_upload_state.json")
    rag_contracts_upload_state_file: str = str(
        _BACKEND_ROOT / "config" / ".rag_contracts_upload_state.json"
    )
    regulatory_documents_prefix: str = "regulatory"
    regulatory_manifest_file: str = str(
        _BACKEND_ROOT / "config" / "REGULATORY_CORPUS_MANIFEST.csv"
    )
    regulatory_staging_dir: str = str(_BACKEND_ROOT / "regulatory_corpus")
    rag_regulatory_state_file: str = str(
        _BACKEND_ROOT / "config" / ".rag_regulatory_state.json"
    )

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""
    gmail_label: str = "LegalOS/MSA"
    gmail_poll_interval_seconds: int = 120
    gmail_enabled: bool = False

    # keycloak_url: str = Field(
    #     default="",
    #     validation_alias=AliasChoices("dev_keycloak_url", "keycloak_url")
    # )
    # keycloak_realm: str = Field(
    #     default="",
    #     validation_alias=AliasChoices("dev_keycloak_realm", "keycloak_realm")
    # )
    # keycloak_client_id: str = "legalos-dev"
    # keycloak_idp_hint: str = ""
    # iam_backend_url: str = ""

    keycloak_client_id: str = ""
    keycloak_idp_hint: str = ""
    iam_backend_url: str = ""
    iam_client_secret: str = ""
    iam_sync_interval_seconds: int = 300
    keycloak_realm: str = ""
    keycloak_url: str = ""

    @property
    def iam_sync_enabled(self) -> bool:
        """True when Central IAM credentials are loaded from Secret Manager."""
        return bool(
            self.iam_backend_url.strip()
            and self.keycloak_client_id.strip()
            and not _is_placeholder_secret(self.iam_client_secret)
        )

    @property
    def keycloak_sso_enabled(self) -> bool:
        """True only for environments listed in _KEYCLOAK_SSO_ENVS.

        To activate SSO in another environment, add its LEGALOS_ENV value to
        _KEYCLOAK_SSO_ENVS at the top of this file — no other changes needed.
        """
        return self.legalos_env.strip().lower() in _KEYCLOAK_SSO_ENVS

    @property
    def smtp_from_address(self) -> str:
        return self.smtp_username

    @property
    def orch_session_dsn(self) -> str:
        return self.orch_session_db_url or self.database_url

    @property
    def vertex_rag_corpus_resource(self) -> str:
        """Full Vertex RAG corpus resource name for legal templates."""
        raw = (self.vertex_rag_corpus_id or "").strip()
        if not raw:
            return ""
        if raw.startswith("projects/"):
            return raw
        project = self.gcp_project_id.strip()
        location = (self.vertex_rag_location or "").strip()
        if not project or not location:
            return ""
        return f"projects/{project}/locations/{location}/ragCorpora/{raw}"

    @property
    def regulatory_vertex_corpus_resource(self) -> str:
        """Full Vertex RAG corpus resource name for the regulatory corpus."""
        raw = (self.regulatory_vertex_corpus_id or "").strip()
        if not raw:
            return ""
        if raw.startswith("projects/"):
            return raw
        project = self.gcp_project_id.strip()
        location = (self.vertex_rag_location or "").strip()
        if not project or not location:
            return ""
        return f"projects/{project}/locations/{location}/ragCorpora/{raw}"

    @property
    def regulatory_vertex_sync_active(self) -> bool:
        """True only when the regulatory Vertex corpus is both enabled and configured."""
        return bool(
            self.regulatory_vertex_sync_enabled
            and self.regulatory_vertex_corpus_resource
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _resolve_gcp_secret_name(self) -> "Settings":
        if self.gcp_secret_name.strip():
            return self
        env_key = self.legalos_env.strip().lower()
        self.gcp_secret_name = _GCP_SECRET_BY_ENV.get(
            env_key,
            f"legalos_{env_key}" if env_key else "legalos_dev",
        )
        return self

    @model_validator(mode="after")
    def _hydrate_from_secret_manager(self) -> "Settings":
        """Fill unset settings from the env-scoped app secret JSON (Infosec).

        Env / ``.env`` always wins. No credentials are hard-coded in this module.
        """
        creds_file = (
            self.gcp_service_account_file
            if self.gcp_service_account_file and os.path.isfile(self.gcp_service_account_file)
            else ""
        )

        # Resolve project id from env/secret later; for the first fetch allow ADC.
        project = self.gcp_project_id.strip() or resolve_gcp_project_id("", creds_file)
        if project and not self.gcp_project_id.strip():
            self.gcp_project_id = project

        data = load_app_secret_dict(self.gcp_project_id, self.gcp_secret_name, creds_file)
        if not data:
            self._fill_iam_sso_from_named_secrets(creds_file)
            self._resolve_smtp_from_named_secrets(creds_file)
            self._warn_missing_required()
            return self

        env_key = self.legalos_env.strip().lower()
        _sso_active = env_key in _KEYCLOAK_SSO_ENVS
        iam_url_key = _IAM_BACKEND_URL_KEY_BY_ENV.get(env_key, "IAM_BACKEND_URL")
        field_map: list[tuple[str, str]] = [
            (iam_url_key if secret_key == "IAM_BACKEND_URL" else secret_key, attr)
            for secret_key, attr in _APP_SECRET_FIELD_MAP
        ]
        if _sso_active:
            field_map.extend(_KEYCLOAK_SSO_KEYS_BY_ENV.get(env_key, ()))

        applied: list[str] = []
        for secret_key, attr in field_map:
            if _env_provided(secret_key):
                continue
            if secret_key not in data:
                continue
            raw = data[secret_key]
            if raw is None or (isinstance(raw, str) and not str(raw).strip()):
                continue
            current = getattr(self, attr)
            try:
                setattr(self, attr, _coerce(raw, current))
                applied.append(secret_key)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping secret key %s: %s", secret_key, exc)

        # UAT prefers UAT_IAM_BACKEND_URL; fall back to IAM_BACKEND_URL if absent.
        if (
            iam_url_key != "IAM_BACKEND_URL"
            and not self.iam_backend_url.strip()
            and not _env_provided("IAM_BACKEND_URL")
            and "IAM_BACKEND_URL" in data
        ):
            raw = data["IAM_BACKEND_URL"]
            if raw is not None and str(raw).strip():
                try:
                    self.iam_backend_url = _coerce(raw, self.iam_backend_url)
                    applied.append("IAM_BACKEND_URL")
                except (TypeError, ValueError) as exc:
                    logger.warning("Skipping secret key IAM_BACKEND_URL: %s", exc)

        # Legacy SMTP_*_SECRET keys only fill gaps (do not clobber SMTP_USERNAME).
        for secret_key, attr in _APP_SECRET_ALIASES:
            if _env_provided(secret_key) or _env_provided(
                "SMTP_USERNAME" if attr == "smtp_username" else "SMTP_PASSWORD"
            ):
                continue
            current = getattr(self, attr)
            if isinstance(current, str) and current.strip():
                continue
            if secret_key not in data:
                continue
            raw = data[secret_key]
            if raw is None or (isinstance(raw, str) and not str(raw).strip()):
                continue
            try:
                setattr(self, attr, _coerce(raw, current))
                applied.append(secret_key)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping secret key %s: %s", secret_key, exc)

        if applied:
            logger.info(
                "Applied %d keys from Secret Manager (%s): %s",
                len(applied),
                self.gcp_secret_name,
                ", ".join(applied),
            )

        # Project id may arrive from the blob after the first resolve attempt.
        if not self.gcp_project_id.strip():
            self.gcp_project_id = resolve_gcp_project_id("", creds_file)

        self._fill_iam_sso_from_named_secrets(creds_file)
        self._resolve_smtp_from_named_secrets(creds_file)
        self._warn_missing_required()
        return self

    def _fill_iam_sso_from_named_secrets(self, creds_file: str) -> None:
        """Fill UAT IAM/SSO fields from standalone SM secrets when the JSON blob omits them.

        DEV is unchanged: it already hydrates from keys inside ``legalos_dev``.
        """
        env_key = self.legalos_env.strip().lower()
        default_client_id = _KEYCLOAK_CLIENT_ID_BY_ENV.get(env_key, "")
        if (
            default_client_id
            and not _env_provided("KEYCLOAK_CLIENT_ID")
            and (not self.keycloak_client_id.strip() or _is_placeholder_secret(self.keycloak_client_id))
        ):
            self.keycloak_client_id = default_client_id

        if env_key != "uat":
            return

        pairs: list[tuple[str, str]] = [
            (_IAM_BACKEND_URL_KEY_BY_ENV.get(env_key, "IAM_BACKEND_URL"), "iam_backend_url"),
            *_KEYCLOAK_SSO_KEYS_BY_ENV.get(env_key, ()),
        ]
        for secret_id, attr in pairs:
            if _env_provided(secret_id):
                continue
            current = getattr(self, attr)
            if isinstance(current, str) and current.strip() and not _is_placeholder_secret(current):
                continue
            value = load_secret_text(self.gcp_project_id, secret_id, creds_file)
            if value:
                setattr(self, attr, value)

    def _resolve_smtp_from_named_secrets(self, creds_file: str) -> None:
        """If username/password still empty, load from dedicated SM secret names."""
        if not self.smtp_username and self.smtp_username_secret_name:
            self.smtp_username = load_secret_text(
                self.gcp_project_id,
                self.smtp_username_secret_name,
                creds_file,
            )
        if not self.smtp_password and self.smtp_password_secret_name:
            self.smtp_password = load_secret_text(
                self.gcp_project_id,
                self.smtp_password_secret_name,
                creds_file,
            )

    def _warn_missing_required(self) -> None:
        missing = [
            name
            for name, ok in (
                ("DATABASE_URL", bool(self.database_url.strip())),
                ("JWT_SECRET", bool(self.jwt_secret.strip())),
            )
            if not ok
        ]
        if missing:
            logger.warning(
                "Missing required settings %s — set via env or Secret Manager (%s)",
                missing,
                self.gcp_secret_name or "unset",
            )


settings = Settings()
