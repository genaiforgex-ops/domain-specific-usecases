"""Text embeddings for the regulatory corpus.

Vectors are truncated to `regulatory_embed_dims` and stored as raw little-endian
float32 bytes, because pgvector is not available on this Postgres instance —
similarity is a cached numpy matmul in `regulatory_rag_service`.

Truncating a Matryoshka embedding leaves it un-normalized (gemini-embedding-001
returns ‖v‖≈0.59 at 768 dims), so every vector is L2-normalized here. That makes
cosine similarity a plain dot product downstream; skip it and every score is
silently wrong.
"""

from __future__ import annotations

import logging

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

DTYPE = np.float32
_TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
_TASK_QUERY = "RETRIEVAL_QUERY"
# Gemini embedding inputs are capped well below this, but a single clause chunk can
# be long; clip rather than fail the whole batch.
_MAX_CHARS_PER_INPUT = 8000


class EmbeddingError(Exception):
    """Raised when embeddings cannot be produced."""


def _client():
    from google import genai

    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY is not configured — cannot embed")
    return genai.Client(api_key=api_key)


def dims() -> int:
    return int(settings.regulatory_embed_dims)


def normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a single vector (zero-safe)."""
    arr = np.asarray(vec, dtype=DTYPE)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return arr
    return (arr / norm).astype(DTYPE)


def to_bytes(vec: np.ndarray) -> bytes:
    return normalize(vec).tobytes()


def from_bytes(blob: bytes | None) -> np.ndarray | None:
    """Decode a stored vector, or None when it is absent or the wrong width."""
    if not blob:
        return None
    if len(blob) % DTYPE().itemsize:
        logger.warning("Stored embedding is not a float32 buffer — reindex required")
        return None
    arr = np.frombuffer(blob, dtype=DTYPE)
    if arr.size != dims():
        logger.warning(
            "Stored embedding has %d dims, expected %d — reindex required", arr.size, dims()
        )
        return None
    return arr


def _embed(texts: list[str], *, task_type: str) -> list[np.ndarray]:
    from google.genai import types as genai_types

    client = _client()
    model = settings.regulatory_embed_model
    payload = [(t or " ")[:_MAX_CHARS_PER_INPUT] for t in texts]

    response = client.models.embed_content(
        model=model,
        contents=payload,
        config=genai_types.EmbedContentConfig(
            output_dimensionality=dims(), task_type=task_type
        ),
    )
    embeddings = list(response.embeddings or [])
    if len(embeddings) != len(payload):
        raise EmbeddingError(
            f"Embedding count mismatch: asked for {len(payload)}, got {len(embeddings)}"
        )
    return [normalize(np.asarray(e.values, dtype=DTYPE)) for e in embeddings]


def embed_documents(texts: list[str], *, batch_size: int | None = None) -> list[bytes]:
    """Embed clause chunks for storage. Returns one packed vector per input."""
    if not texts:
        return []
    size = max(1, int(batch_size or settings.regulatory_embed_batch))
    out: list[bytes] = []
    for start in range(0, len(texts), size):
        batch = texts[start : start + size]
        vectors = _embed(batch, task_type=_TASK_DOCUMENT)
        out.extend(v.tobytes() for v in vectors)
        logger.info("Embedded %d/%d chunks", len(out), len(texts))
    return out


def embed_query(text: str) -> np.ndarray:
    """Embed a search query. Asymmetric task type matters for retrieval quality."""
    query = (text or "").strip()
    if not query:
        raise EmbeddingError("Cannot embed an empty query")
    return _embed([query], task_type=_TASK_QUERY)[0]
