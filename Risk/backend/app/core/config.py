from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from repo root (parent of backend/) when running locally from backend/
_env_files: list[str] = []
for parent in [Path.cwd(), Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[3]]:
    candidate = parent / ".env"
    if candidate.is_file():
        _env_files.append(str(candidate))
        break
if not _env_files:
    _env_files = [".env"]


class Settings(BaseSettings):
    """All configuration loads from environment / .env — no cloud secret manager."""

    model_config = SettingsConfigDict(
        env_file=_env_files[0] if _env_files else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://genaiforge:genaiforge@localhost:5433/genaiforge"
    database_url_sync: str = "postgresql://genaiforge:genaiforge@localhost:5433/genaiforge"

    local_storage_path: str = "/tmp/genaiforge-documents"

    gcs_bucket: str = "genaiforge"
    gcs_prefix: str = "Outsourcing Classification docs"

    sso_adapter: str = "jwt"
    osint_adapter: str = "mock"
    email_adapter: str = "mock"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_from: str = "noreply@genaiforge.local"
    smtp_username: str = ""
    smtp_password: str = ""
    storage_adapter: str = "local"

    secret_key: str = "change-me-in-production-genaiforge"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5174,http://localhost:5173,http://localhost:3000"
    environment: str = "local"

    access_token_expire_minutes: int = 480
    auth_dev_mode: bool = False

    gemini_api_key: str = ""

    public_base_url: str = "http://localhost:8002"
    frontend_base_url: str = "http://localhost:5174"

    # Seed password for demo accounts created on startup (override via .env)
    seed_password: str = "demo1234"

    m1_use_code_prompt: bool = True
    m1_confidence_threshold: float = 0.70
    m1_retrieval_top_k: int = 0

    @property
    def is_local_dev(self) -> bool:
        return self.environment in {"development", "local", "dev"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
