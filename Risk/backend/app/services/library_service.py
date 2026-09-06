import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.models.classification import RegulationDocument, RegulatorClause
from app.scripts.regulation_ingest.extract_pdf import extract_blocks_from_bytes
from app.scripts.regulation_ingest.load_clauses import build_clause_rows


class LibraryService:
    """Self-service regulation PDF ingestion ('Library' tab). Reuses the same
    extract/chunk pipeline as the CLI script (app/scripts/regulation_ingest/
    load_clauses.py) — this class only adds the document lifecycle
    (pending_review -> active -> archived) and DB-backed PDF storage around
    it."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def create_document(
        self,
        regulator: str,
        instrument: str,
        source_doc: str,
        ref_prefix: str,
        filename: str,
        pdf_bytes: bytes,
        uploaded_by: uuid.UUID | None,
    ) -> RegulationDocument:
        """Fast, synchronous step: persist the upload and return immediately
        with an id the caller can poll — the actual PDF extraction (slow for
        a 90-page circular) happens in process_document(), scheduled as a
        background task, matching how classification jobs already separate
        creation from execution."""
        document = RegulationDocument(
            id=uuid.uuid4(),
            regulator=regulator,
            instrument=instrument,
            source_doc=source_doc,
            ref_prefix=ref_prefix,
            filename=filename,
            pdf_bytes=pdf_bytes,
            status="processing",
            # version is String(32); "doc-" + 24 hex chars comfortably fits
            # while still being unique enough — real linkage for
            # classification is via document_id, this is just a legible tag.
            version=f"doc-{uuid.uuid4().hex[:24]}",
            uploaded_by=uploaded_by,
        )
        self.db.add(document)
        await self.audit.log(
            "library.upload",
            "regulation_document",
            str(document.id),
            actor_id=uploaded_by,
            payload={"regulator": regulator, "instrument": instrument},
        )
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def process_document(self, document_id: uuid.UUID) -> RegulationDocument:
        """Extract/chunk an already-created document's stored PDF bytes into
        RegulatorClause rows. Moves status processing -> pending_review, or
        -> failed if chunk_clauses.py's regex doesn't match this PDF's
        numbering style (see chunk_clauses.py docstring — a heuristic, not
        guaranteed for every document)."""
        document = await self._get(document_id)
        try:
            blocks = extract_blocks_from_bytes(document.pdf_bytes)
            rows = build_clause_rows(
                blocks,
                document.regulator,
                document.instrument,
                document.source_doc,
                document.ref_prefix,
                document.version,
                document_id=document.id,
            )
        except ValueError as e:
            document.status = "failed"
            await self.audit.log(
                "library.ingest_failed",
                "regulation_document",
                str(document.id),
                payload={"error": str(e)},
            )
            await self.db.flush()
            await self.db.refresh(document)
            return document

        self.db.add_all(rows)
        document.status = "pending_review"
        await self.audit.log(
            "library.ingested",
            "regulation_document",
            str(document.id),
            payload={"clause_count": len(rows)},
        )
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def activate_document(self, document_id: uuid.UUID, actor_id: uuid.UUID | None) -> RegulationDocument:
        document = await self._get(document_id)
        if document.status not in ("pending_review", "archived"):
            raise ValueError(f"Cannot activate a document in status={document.status!r}")
        before = {"status": document.status}
        document.status = "active"
        document.activated_at = datetime.now(timezone.utc)
        await self.audit.log(
            "library.activate",
            "regulation_document",
            str(document.id),
            actor_id=actor_id,
            before=before,
            after={"status": "active"},
        )
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def archive_document(self, document_id: uuid.UUID, actor_id: uuid.UUID | None) -> RegulationDocument:
        document = await self._get(document_id)
        before = {"status": document.status}
        document.status = "archived"
        document.archived_at = datetime.now(timezone.utc)
        await self.audit.log(
            "library.archive",
            "regulation_document",
            str(document.id),
            actor_id=actor_id,
            before=before,
            after={"status": "archived"},
        )
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def list_documents(self) -> list[dict]:
        result = await self.db.execute(
            select(
                RegulationDocument,
                func.count(RegulatorClause.id).label("clause_count"),
            )
            .outerjoin(RegulatorClause, RegulatorClause.document_id == RegulationDocument.id)
            .group_by(RegulationDocument.id)
            .order_by(RegulationDocument.created_at.desc())
        )
        return [{"document": doc, "clause_count": count} for doc, count in result.all()]

    async def get_document_clauses(self, document_id: uuid.UUID) -> list[RegulatorClause]:
        result = await self.db.execute(
            select(RegulatorClause).where(RegulatorClause.document_id == document_id)
        )
        return list(result.scalars().all())

    async def _get(self, document_id: uuid.UUID) -> RegulationDocument:
        result = await self.db.execute(
            select(RegulationDocument).where(RegulationDocument.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"No regulation document with id {document_id}")
        return document
