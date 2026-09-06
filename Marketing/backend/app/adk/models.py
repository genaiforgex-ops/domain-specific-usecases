"""Model wiring for the ADK backend — resolves the Gemini model from config.

ADK reads GOOGLE_API_KEY from the environment. We mirror the app's `settings`
value into it here (using AI Studio, not Vertex), so config.py stays the single
place that *reads* configuration while the SDK gets what it expects.
"""

import os

from app.config import settings


def configure_genai() -> None:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    if settings.gemini_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key


def build_model() -> str:
    return settings.gemini_model
