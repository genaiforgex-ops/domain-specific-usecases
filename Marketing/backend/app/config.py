import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class EmailSettings(BaseSettings):
    """All email/notification config — env prefix ``EMAIL_``."""

    model_config = SettingsConfigDict(
        env_prefix="EMAIL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    enabled: bool = False
    from_name: str = "GenAIForge Marketing"
    from_address: str = ""

    app_base_url: str = "http://localhost:5180"
    api_base_url: str = "http://localhost:8000"
    approval_token_secret: str = ""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""


@lru_cache
def get_email_settings() -> EmailSettings:
    return EmailSettings()


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env only."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/orchestration"

    environment: str = "local"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_alg: str = "HS256"
    access_token_expire_minutes: int = 720

    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"

    public_base_url: str = ""
    frontend_base_url: str = ""

    run_migrations_on_startup: bool = True

    seed_on_startup: bool = True
    seed_password: str = "demo1234"
    seed_admin_email: str = "admin@genaiforge.in"
    seed_admin_full_name: str = "Meera Krishnan"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    image_model: str = "gemini-2.5-flash-image"
    image_size: str = "2K"

    figma_oauth_path: str = "~/.config/figma_agent/oauth.json"
    figma_mcp_url: str = "https://mcp.figma.com/mcp"
    figma_redirect_uri: str = "http://localhost:8000/api/figma/callback"
    figma_oauth_client_name: str = "Claude Code"
    figma_post_login_redirect: str = "http://localhost:5180"
    figma_plan_key: str = ""
    brand_assets_dir: str = str(Path(__file__).resolve().parents[1] / "assets")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def email(self) -> EmailSettings:
        return get_email_settings()

    @property
    def is_local_dev(self) -> bool:
        return self.environment in {"development", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
