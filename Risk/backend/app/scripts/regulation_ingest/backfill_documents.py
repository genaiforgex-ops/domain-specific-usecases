"""One-time backfill: give the 3 legacy startup-seeded PDFs (main.py's
_seed_clauses_if_needed, version='v3') a regulation_documents row each, and
link their existing regulator_clauses rows to it via document_id.

Run once per environment, after migration 006:

    python -m app.scripts.regulation_ingest.backfill_documents

Idempotent — skips a (regulator, instrument) pair if a regulation_documents
row for it already exists. After this runs, regulator_clauses.document_id is
populated for all 3 legacy PDFs, and app/api/v1/classifications.py's PDF
routes serve them from the DB like any Library upload — the old
_INSTRUMENT_PDF/_REGULATIONS_DIR disk lookup is retired.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.models.classification import RegulationDocument, RegulatorClause

_REGULATIONS_DIR = Path(__file__).resolve().parents[3] / "resources" / "regulations"

_SPECS = [
    (
        "rbi_nbfc_outsourcing_2025.pdf", "RBI", "NBFC",
        "RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025", "RBI-NBFC-2025",
    ),
    (
        "rbi_payments_bank_outsourcing_2025.pdf", "RBI", "PAYMENTS_BANK",
        "RBI (Payments Banks - Managing Risks in Outsourcing) Directions, 2025", "RBI-PB-2025",
    ),
    (
        "sebi_ia_master_circular_2025.pdf", "SEBI", "IA",
        "SEBI Master Circular for Investment Advisers, 2025", "SEBI-MC-IA-2025",
    ),
]


async def backfill() -> int:
    created = 0
    async with async_session_factory() as session:
        for filename, regulator, instrument, source_doc, ref_prefix in _SPECS:
            existing = await session.execute(
                select(RegulationDocument).where(
                    RegulationDocument.regulator == regulator,
                    RegulationDocument.instrument == instrument,
                )
            )
            if existing.scalar_one_or_none():
                print(f"[backfill] {regulator}/{instrument} already has a document, skipping")
                continue

            path = _REGULATIONS_DIR / filename
            if not path.exists():
                print(f"[backfill] {path} not found, skipping")
                continue

            now = datetime.now(timezone.utc)
            document = RegulationDocument(
                id=uuid.uuid4(),
                regulator=regulator,
                instrument=instrument,
                source_doc=source_doc,
                ref_prefix=ref_prefix,
                filename=filename,
                pdf_bytes=path.read_bytes(),
                status="active",
                version="v3",
                activated_at=now,
            )
            session.add(document)
            await session.flush()

            result = await session.execute(
                update(RegulatorClause)
                .where(
                    RegulatorClause.regulator == regulator,
                    RegulatorClause.instrument == instrument,
                    RegulatorClause.version == "v3",
                )
                .values(document_id=document.id)
            )
            print(f"[backfill] created document for {regulator}/{instrument}, linked {result.rowcount} clauses")
            created += 1

        await session.commit()
    return created


def main() -> None:
    count = asyncio.run(backfill())
    print(f"Backfilled {count} regulation document(s)")


if __name__ == "__main__":
    main()
