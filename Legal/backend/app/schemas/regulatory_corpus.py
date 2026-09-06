"""Wire contracts for the regulatory corpus admin surface."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CorpusDocOut(BaseModel):
    """A manifest row joined with its ingestion state."""

    doc_id: str
    title: str
    issuer: str
    domain: str
    doc_type: str
    priority: str
    update_cadence: str
    download_mode: str
    official_url: str | None = None
    direct_pdf_url: str | None = None
    version_or_effective: str = ""
    effective_date: str | None = None
    status: str
    chunk_count: int = 0
    page_count: int = 0
    ingested_at: str | None = None
    superseded_by: str | None = None
    supersedes: list[str] = []
    tags: list[str] = []
    storage_key: str | None = None
    last_error: str | None = None
    can_auto_fetch: bool = False


class CorpusTotals(BaseModel):
    manifest_total: int
    ingested: int
    chunks: int


class CorpusOverview(BaseModel):
    totals: CorpusTotals
    documents: list[CorpusDocOut]


class IngestResultOut(BaseModel):
    doc_id: str
    status: str
    chunk_count: int = 0
    page_count: int = 0
    skipped: bool = False
    message: str = ""


class ChunkOut(BaseModel):
    """One clause chunk — used to eyeball chunking quality before trusting it."""

    model_config = ConfigDict(from_attributes=True)

    chunk_key: str
    section_label: str | None = None
    parent_heading: str | None = None
    ordinal: int
    page: int
    token_count: int
    text: str


class ReindexResult(BaseModel):
    reindexed: int
