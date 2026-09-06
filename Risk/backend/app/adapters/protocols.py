from dataclasses import dataclass
from typing import Protocol

from starlette.requests import Request

MAX_CLASSIFY_TEXT_CHARS = 120_000


@dataclass
class Identity:
    email: str
    display_name: str
    groups: list[str]


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    evidence: list[dict]
    clause_ids: list[str]
    model_version: str
    reasoning: str = ""
    truncated: bool = False
    # Token usage reported by the model provider (None when unavailable, e.g. the
    # fallback path). Used for usage/metrics accounting, never for logic.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class OSINTFinding:
    category: str
    title: str
    summary: str
    source_tier: str
    source_url: str
    severity_weight: float


class SSOAdapter(Protocol):
    async def get_identity(self, request: Request) -> Identity | None: ...


class AIAdapter(Protocol):
    async def classify(
        self,
        text: str,
        clauses: list[dict],
        module: str = "M1",
        regulator: str = "RBI",
        system_prompt: str | None = None,
    ) -> ClassificationResult: ...

    async def score_suggest(self, intake: dict) -> dict: ...


class OSINTAdapter(Protocol):
    async def gather(self, vendor: dict) -> list[OSINTFinding]: ...

    async def audit(self, vendor: dict) -> dict:
        """Rich BLANK_AUDIT-shaped vendor due-diligence report.

        The service stores this and derives flat findings + a red-flag
        score from it.
        """
        ...


class EmailAdapter(Protocol):
    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        *,
        cc: list[str] | None = None,
        html: str | None = None,
    ) -> str:
        """Send one message. `body` is the plain-text part; `html`, when given,
        rides along as a multipart/alternative so clients that can render it do.
        Addresses in `cc` are visible to every recipient."""
        ...


class StorageAdapter(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...
    async def download(self, key: str) -> bytes: ...
    async def get_url(self, key: str) -> str: ...
