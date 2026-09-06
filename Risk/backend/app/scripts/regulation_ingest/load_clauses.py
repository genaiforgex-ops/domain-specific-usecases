"""Parse a regulation PDF end-to-end and upsert verbatim, page/para-located
clauses into regulator_clauses.

Run once per source document, after dropping the PDF under
backend/resources/regulations/:

    python -m app.scripts.regulation_ingest.load_clauses \\
        --pdf resources/regulations/rbi_nbfc_outsourcing_2025.pdf \\
        --regulator RBI --instrument NBFC \\
        --source-doc "RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025" \\
        --ref-prefix RBI-NBFC-2025 --version v3

    python -m app.scripts.regulation_ingest.load_clauses \\
        --pdf resources/regulations/rbi_payments_bank_outsourcing_2025.pdf \\
        --regulator RBI --instrument PAYMENTS_BANK \\
        --source-doc "RBI (Payments Banks - Managing Risks in Outsourcing) Directions, 2025" \\
        --ref-prefix RBI-PB-2025 --version v3

    python -m app.scripts.regulation_ingest.load_clauses \\
        --pdf resources/regulations/sebi_ia_master_circular_2025.pdf \\
        --regulator SEBI --instrument IA \\
        --source-doc "SEBI Master Circular for Investment Advisers, 2025" \\
        --ref-prefix SEBI-MC-IA-2025 --version v3

Idempotent: re-running deletes and re-inserts rows for the same
(regulator, instrument, version) triple, same delete-then-insert pattern
migration 004 used for its hand-curated seed — except this is real
ingestion from the source PDF, not hand-typed paraphrase, so it lives in a
script rather than a migration. Alembic stays schema-only from here on
(see migration 005); clause content lives in this script + the checked-in
PDFs under backend/resources/regulations/.

get_active_clause_version() in classification_service.py always picks the
version with the latest effective_from, so loading a fresh "v3" here makes
it active automatically without touching jobs already pinned to "v1"/"v2".
"""
import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete

from app.core.database import async_session_factory
from app.models.classification import RegulatorClause
from app.scripts.regulation_ingest.chunk_clauses import build_clause_ref, chunk_paragraphs, derive_tags
from app.scripts.regulation_ingest.extract_pdf import extract_blocks


def build_clause_rows(
    blocks: list[dict],
    regulator: str,
    instrument: str,
    source_doc: str,
    ref_prefix: str,
    version: str,
    document_id: uuid.UUID | None = None,
) -> list[RegulatorClause]:
    """Shared by the CLI path (load(), below) and the Library upload path
    (library_service.ingest_document) — turns extracted blocks into
    RegulatorClause rows without touching the database."""
    chunks = chunk_paragraphs(blocks)
    if not chunks:
        raise ValueError(
            "No numbered paragraphs found — chunk_clauses.py's regex may not "
            "match this document's numbering style, check manually."
        )

    now = datetime.now(timezone.utc)
    return [
        RegulatorClause(
            id=uuid.uuid4(),
            version=version,
            effective_from=now,
            regulator=regulator,
            clause_ref=build_clause_ref(ref_prefix, chunk),
            text=chunk["text"],
            tags=derive_tags(chunk["text"]),
            instrument=instrument,
            source_doc=source_doc,
            page_no=chunk["page_no"],
            para_no=chunk["para_no"],
            document_id=document_id,
        )
        for chunk in chunks
    ]


async def load(
    pdf_path: str,
    regulator: str,
    instrument: str,
    source_doc: str,
    ref_prefix: str,
    version: str,
) -> int:
    blocks = extract_blocks(pdf_path)
    rows = build_clause_rows(blocks, regulator, instrument, source_doc, ref_prefix, version)

    async with async_session_factory() as session:
        await session.execute(
            delete(RegulatorClause).where(
                RegulatorClause.regulator == regulator,
                RegulatorClause.instrument == instrument,
                RegulatorClause.version == version,
            )
        )
        session.add_all(rows)
        await session.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", required=True, help="path to the source regulation PDF")
    parser.add_argument("--regulator", required=True, choices=["RBI", "SEBI"])
    parser.add_argument("--instrument", required=True, help='e.g. "NBFC", "PAYMENTS_BANK", "IA"')
    parser.add_argument("--source-doc", required=True, help="human-readable title for citation")
    parser.add_argument("--ref-prefix", required=True, help='e.g. "RBI-NBFC-2025"')
    parser.add_argument("--version", default="v3", help="clause_library_version tag")
    args = parser.parse_args()

    count = asyncio.run(
        load(args.pdf, args.regulator, args.instrument, args.source_doc, args.ref_prefix, args.version)
    )
    print(
        f"Loaded {count} clauses from {args.pdf} as {args.regulator}/{args.instrument} "
        f"version={args.version}"
    )


if __name__ == "__main__":
    main()
