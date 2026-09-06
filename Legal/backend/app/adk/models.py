"""Provider-agnostic ADK model construction.

`build_model()` returns whatever ADK needs as an agent's `model=` argument:

  - A bare model-name string (e.g. "gemini-2.0-flash") makes ADK call Gemini
    directly. Used for dev / pilot. Requires `gemini_api_key`.

  - A `LiteLlm(...)` instance routes the call through LiteLLM to any
    OpenAI-compatible / Ollama / vLLM endpoint. This is the production path:
    point `ADK_MODEL` at e.g. "ollama/llama3.1" or "openai/<deployed-model>"
    and `ADK_LITELLM_API_BASE` at the on-prem gateway so legal data never
    leaves JFPSL infra (see ai_service.py BRD constraint).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings

logger = logging.getLogger("legalos.adk")

# Models whose name implies a non-Gemini provider routed via LiteLLM.
_LITELLM_PREFIXES = ("ollama/", "openai/", "vllm/", "hosted_vllm/", "azure/", "bedrock/")


def is_gemini_direct(model_name: str) -> bool:
    return model_name.startswith("gemini") and "/" not in model_name


def build_model(model_name: str | None = None) -> Any:
    """Return an ADK-compatible model handle for the configured backend."""
    model_name = model_name or settings.adk_model

    if is_gemini_direct(model_name):
        # ADK's Gemini integration (google.genai) reads the key from the
        # environment, accepting either GOOGLE_API_KEY or GEMINI_API_KEY. Assign
        # directly (not setdefault): the container often has the var set to an
        # empty string, which setdefault would not overwrite — so the real key
        # loaded from Secret Manager (settings.gemini_api_key) would never reach
        # google.genai. settings is the single source of truth here.
        has_key = bool(settings.gemini_api_key)
        # Never log the key itself — only whether it is present. A missing key
        # here is the usual reason prod silently falls back to the stub.
        logger.info(
            "ADK model resolved: provider=gemini-direct model=%s gemini_api_key_present=%s",
            model_name,
            has_key,
        )
        if not has_key:
            logger.warning(
                "ADK gemini-direct selected but gemini_api_key is EMPTY — the agent call "
                "will fail and degrade to the deterministic stub. Set GEMINI_API_KEY "
                "in the pod env, or provide GCP credentials (Workload "
                "Identity / service-account) so Secret Manager '%s' can be read.",
                settings.gcp_secret_name,
            )
        if settings.gemini_api_key:
            # Feed our single source of truth to google.genai under the same
            # name we configure everywhere else (GEMINI_API_KEY). The SDK
            # accepts it; empty GOOGLE_API_KEY in the env is ignored (falsy).
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
        # Use the AI-Studio (api key) path rather than Vertex unless told otherwise.
        if not os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
        return model_name

    # Anything else → LiteLLM (on-prem / self-hosted).
    from google.adk.models.lite_llm import LiteLlm

    kwargs: dict[str, Any] = {"model": model_name}
    if settings.adk_litellm_api_base:
        kwargs["api_base"] = settings.adk_litellm_api_base
    if settings.adk_litellm_api_key:
        kwargs["api_key"] = settings.adk_litellm_api_key
    logger.info(
        "ADK model resolved: provider=litellm model=%s api_base=%s api_key_present=%s",
        model_name,
        settings.adk_litellm_api_base or "(none)",
        bool(settings.adk_litellm_api_key),
    )
    return LiteLlm(**kwargs)
