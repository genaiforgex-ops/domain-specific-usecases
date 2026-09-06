"""Unit tests for the Vertex RAG retrieval call shape.

The API rejects `rag_retrieval_config` inside `vertex_rag_store` with a
400 INVALID_ARGUMENT that the service swallows, so a malformed call silently
degrades every answer to web snippets. These tests pin the working shape.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from app.services import jfpsl_rag_service

_CORPUS = "projects/p/locations/asia-south1/ragCorpora/1"


@contextmanager
def _configured_corpus(resource: str = _CORPUS):
    """`vertex_rag_corpus_resource` is a property, so it has to be patched on the class."""
    with patch.object(
        type(jfpsl_rag_service.settings),
        "vertex_rag_corpus_resource",
        new_callable=PropertyMock,
        return_value=resource,
    ):
        yield


class _RagStub:
    """Captures the kwargs the service passes to retrieve_contexts."""

    def __init__(self, contexts: list[SimpleNamespace] | None = None) -> None:
        self.calls: list[dict] = []
        self._contexts = contexts or []

    def retrieve_contexts(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            contexts=SimpleNamespace(contexts=self._contexts)
        )


def _run(contexts: list[SimpleNamespace] | None = None, *, max_results: int = 3):
    rag = _RagStub(contexts)
    client = SimpleNamespace(rag=rag)
    with patch.object(
        jfpsl_rag_service, "_agent_client", return_value=client
    ), _configured_corpus():
        out = jfpsl_rag_service.search_jfpsl_corpus("indemnity", max_results=max_results)
    return out, rag.calls


def test_top_k_is_on_the_query_not_the_store() -> None:
    _, calls = _run(max_results=4)
    assert len(calls) == 1
    kwargs = calls[0]

    store = kwargs["vertex_rag_store"]
    assert not hasattr(store, "rag_retrieval_config") or store.rag_retrieval_config is None

    query = kwargs["query"]
    assert query["text"] == "indemnity"
    assert query["similarity_top_k"] == 4


def test_corpus_resource_is_passed_as_rag_resource() -> None:
    _, calls = _run()
    resources = calls[0]["vertex_rag_store"].rag_resources
    assert [r.rag_corpus for r in resources] == [_CORPUS]


def test_retrieved_context_is_rendered_with_citation_index() -> None:
    ctx = SimpleNamespace(
        text="8.1 Limitation of Liability. In no event shall either Party...",
        source_display_name="Template-MSA",
        source_uri=None,
        score=0.42,
    )
    out, _ = _run([ctx])
    assert "Template-MSA" in out
    assert "1. " in out
    assert "Limitation of Liability" in out


def test_retrieval_failure_degrades_without_raising() -> None:
    class _Boom:
        def retrieve_contexts(self, **_kwargs):
            raise RuntimeError("400 INVALID_ARGUMENT")

    with patch.object(
        jfpsl_rag_service, "_agent_client", return_value=SimpleNamespace(rag=_Boom())
    ), _configured_corpus():
        out = jfpsl_rag_service.search_jfpsl_corpus("indemnity")
    assert "Could not retrieve" in out


def test_empty_result_tells_the_model_to_fall_back() -> None:
    out, _ = _run([])
    assert "No matching legal templates" in out
    assert jfpsl_rag_service.is_rag_insufficient(out)
