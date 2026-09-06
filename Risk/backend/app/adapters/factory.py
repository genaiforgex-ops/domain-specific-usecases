import logging
from functools import lru_cache

from app.adapters.email.mock_email import MockEmailAdapter
from app.adapters.sso.mock_sso import MockSSOAdapter
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_sso_adapter():
    settings = get_settings()
    if settings.sso_adapter == "mock":
        return MockSSOAdapter()
    from app.adapters.sso.jwt_sso import JWTSSOAdapter
    return JWTSSOAdapter()


@lru_cache
def get_ai_adapter():
    # M1 classification runs on Gemini only — the mock adapter was removed once
    # the real clause library (v3) and grounding were in place.
    from app.adapters.ai.gemini_llm import GeminiLLMAdapter
    return GeminiLLMAdapter()


@lru_cache
def get_osint_adapter():
    from app.adapters.osint.gemini_osint import GeminiOSINTAdapter
    return GeminiOSINTAdapter()


@lru_cache
def get_email_adapter():
    settings = get_settings()
    if settings.email_adapter == "smtp":
        # Falling back to mock here used to be silent, which is the worst failure
        # mode this seam has: mail "sends" successfully forever and nothing tells
        # you SMTP_HOST was never set.
        if not settings.smtp_host:
            logger.warning(
                "EMAIL_ADAPTER=smtp but SMTP_HOST is empty — falling back to the "
                "mock adapter. No mail will actually be sent."
            )
        else:
            from app.adapters.email.smtp_email import SMTPEmailAdapter
            return SMTPEmailAdapter(
                host=settings.smtp_host,
                port=settings.smtp_port,
                from_addr=settings.smtp_from,
                username=settings.smtp_username,
                password=settings.smtp_password,
            )
    return MockEmailAdapter()


@lru_cache
def get_storage_adapter():
    # Imports are local so a backend without google-cloud-storage installed can
    # still run on the local-disk adapter.
    settings = get_settings()
    if settings.storage_adapter == "gcs":
        from app.adapters.storage.gcs_storage import GCSStorageAdapter
        return GCSStorageAdapter()
    if settings.storage_adapter == "local":
        from app.adapters.storage.local_storage import LocalStorageAdapter
        return LocalStorageAdapter()
    raise ValueError(
        f"Unknown STORAGE_ADAPTER={settings.storage_adapter!r}; expected 'gcs' or 'local'"
    )
