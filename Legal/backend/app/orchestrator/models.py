"""Wire-contract DTOs for the chatbot orchestrator.

These are the request/response shapes for the SSE + fallback chat endpoints and
the `@`-mention / attachment context references. Kept separate from the ADK
`Session`/`Event` objects and from the ORM models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContextRef(BaseModel):
    """A single piece of context the user has attached or `@`-mentioned.

    Resolved server-side into text via existing LegalOS services (MSA versions,
    Gmail threads, uploaded documents, knowledge base). Mirrors the context
    handling already present in the legacy `POST /api/legal-bot/ask` endpoint.
    """

    kind: Literal["msa_version", "gmail_thread", "attachment", "kb_entry"]
    # msa_version
    tracker_id: int | None = None
    version_id: int | None = None
    # gmail_thread
    gmail_thread_id: str | None = None
    # attachment (uploaded via POST /api/chat/attachments)
    attachment_id: str | None = None
    # kb_entry
    kb_entry_id: int | None = None
    # Human-readable label for the UI chip.
    label: str | None = None


class ChatRequest(BaseModel):
    """Primary chat request body for `/api/chat/sse` and `/api/chat`.

    `session_id` is optional; when omitted a new session is created and returned
    in the final SSE payload. `user_id` is derived from the authenticated user
    server-side, but accepted here for parity with the blueprint contract.
    """

    text: str = Field(min_length=1)
    session_id: str | None = None
    generate_headline: bool = False
    # Interaction mode chosen in the composer:
    #   review   — answer/analyse grounded in the user's documents (default)
    #   research — research the question broadly and cite the knowledge base
    #   draft    — help draft a document, using any attached templates
    mode: Literal["review", "research", "draft"] = "review"
    context: list[ContextRef] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """One row in the sidebar session list."""

    session_id: str
    title: str
    last_message_preview: str | None = None
    turn_count: int = 0
    updated_at: str | None = None
    # Set only for sessions shared *with* the caller (the owner's display name).
    shared_by: str | None = None


class ShareUser(BaseModel):
    """A user the caller can share a chat with (share-picker directory)."""

    id: int
    email: str
    full_name: str
    role: str


class ShareRequest(BaseModel):
    """Share a session with one or more users, by email."""

    emails: list[str] = Field(min_length=1)


class ShareResult(BaseModel):
    shared_with: list[str] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)


class ChatShareEntry(BaseModel):
    user_id: int
    email: str
    full_name: str
    shared_at: str | None = None


class TemplateAttachRequest(BaseModel):
    storage_key: str = Field(min_length=1)


class Source(BaseModel):
    """A single reference the assistant used to ground an answer."""

    kind: Literal["web", "template", "executed", "attachment", "regulation"] = "web"
    title: str
    url: str | None = None
    snippet: str | None = None
    site: str | None = None
    # GCS object path under legal_templates/, contracts/ or regulatory/ for preview.
    storage_key: str | None = None
    # 1-indexed page when known (Vertex page span or client estimate).
    page: int | None = None
    # Chunk-level grounding (claim ↔ excerpt). Optional for legacy turns.
    chunk_id: str | None = None
    chunk_text: str | None = None
    attachment_id: str | None = None
    label: str | None = None
    # Regulatory clause provenance (kind="regulation"). `section_label` is what the
    # cite chip shows instead of "Page N", so a citation names the provision.
    doc_id: str | None = None
    section_label: str | None = None
    issuer: str | None = None
    effective_date: str | None = None
    superseded_by: str | None = None
    canonical_url: str | None = None


class ThoughtItem(BaseModel):
    """A link or document shown inside a Thought step."""

    title: str
    url: str | None = None
    storage_key: str | None = None
    kind: str | None = None


class ThoughtStep(BaseModel):
    """One step in the LawGenie Thoughts panel."""

    id: str
    kind: Literal["plan", "search", "links", "documents", "status"] = "status"
    title: str = "Thinking"
    detail: str | None = None
    items: list[ThoughtItem] = Field(default_factory=list)


class TurnOut(BaseModel):
    """One persisted turn when replaying a session's history."""

    role: Literal["user", "assistant"]
    text: str
    created_at: str | None = None
    # Assistant turns only: durable turn id, references, and any saved rating.
    turn_id: int | None = None
    sources: list[Source] = Field(default_factory=list)
    thoughts: list[ThoughtStep] = Field(default_factory=list)
    feedback: Literal["up", "down"] | None = None
    feedback_comment: str | None = None
    mode: Literal["review", "research", "draft"] | None = None


class FeedbackRequest(BaseModel):
    """Rate an assistant turn: 'up' / 'down' / null to clear, plus optional detail."""

    value: Literal["up", "down"] | None = None
    comment: str | None = None


class AttachmentOut(BaseModel):
    """Result of uploading a document to attach to the conversation."""

    attachment_id: str
    filename: str
    char_count: int
