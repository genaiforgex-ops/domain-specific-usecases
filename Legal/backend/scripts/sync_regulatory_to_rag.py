#!/usr/bin/env python3
"""Bulk-ingest official regulatory documents into the clause corpus.

The legal team downloads statutes / master directions / circulars from the
regulator's own site into a staging folder, naming each file after its manifest
doc_id (``LEND-DLD-2025.pdf``, ``AML-MD-KYC.pdf``). This script chunks them
clause by clause, embeds them, and stores them so LawGenie can cite provisions.

Mirrors ``sync_contracts_to_rag.py``'s state-file pattern; upload state lives in
``config/.rag_regulatory_state.json`` (gitignored).

Usage:
    python backend/scripts/sync_regulatory_to_rag.py                 # whole staging dir
    python backend/scripts/sync_regulatory_to_rag.py --dry-run
    python backend/scripts/sync_regulatory_to_rag.py --force
    python backend/scripts/sync_regulatory_to_rag.py --doc-id LEND-DLD-2025
    python backend/scripts/sync_regulatory_to_rag.py --direct-only   # fetch download_mode=direct
    python backend/scripts/sync_regulatory_to_rag.py --dir /tmp/regulatory
    python backend/scripts/sync_regulatory_to_rag.py --list          # show corpus status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED = {".pdf", ".docx", ".doc", ".txt", ".html", ".htm"}


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_state(path: Path) -> dict:
    if not path.is_file():
        return {"files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"files": {}}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _doc_id_for(path: Path, known: set[str]) -> str | None:
    """Match a staged filename to a manifest doc_id.

    Accepts an exact stem (``LEND-DLD-2025.pdf``) or a doc_id prefix followed by a
    separator (``LEND-DLD-2025 - digital lending.pdf``), longest match first so
    overlapping ids can't be confused.
    """
    stem = path.stem.strip()
    if stem in known:
        return stem
    upper = stem.upper()
    for doc_id in sorted(known, key=len, reverse=True):
        if upper.startswith(doc_id.upper()):
            rest = upper[len(doc_id) :]
            if not rest or rest[0] in " _-.":
                return doc_id
    return None


def _staged_files(staging_dir: Path) -> list[Path]:
    if not staging_dir.is_dir():
        return []
    return [
        p
        for p in sorted(staging_dir.iterdir())
        if p.is_file() and p.suffix.lower() in _ALLOWED and p.stat().st_size > 0
    ]


def main() -> int:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings
    from app.database import SessionLocal
    from app.services.regulatory_ingest_service import (
        IngestError,
        apply_supersession,
        corpus_status,
        corpus_totals,
        fetch_direct,
        ingest_document,
    )
    from app.services.regulatory_manifest import load_manifest

    parser = argparse.ArgumentParser(
        description="Ingest regulatory documents into the LegalOS clause corpus."
    )
    parser.add_argument(
        "--dir",
        default=settings.regulatory_staging_dir,
        help="Staging directory of downloaded documents named by doc_id.",
    )
    parser.add_argument("--doc-id", help="Ingest only this manifest doc_id.")
    parser.add_argument(
        "--direct-only",
        action="store_true",
        help="Skip the staging dir; download manifest rows with download_mode=direct.",
    )
    parser.add_argument("--force", action="store_true", help="Re-ingest unchanged files.")
    parser.add_argument("--dry-run", action="store_true", help="Report actions only.")
    parser.add_argument("--list", action="store_true", help="Print corpus status and exit.")
    args = parser.parse_args()

    manifest = load_manifest()
    db = SessionLocal()
    try:
        if args.list:
            for row in corpus_status(db):
                flag = {"ingested": "OK  ", "stale": "STALE", "failed": "FAIL", "missing": "--  "}
                mark = flag.get(row.status, row.status)
                extra = f"{row.chunk_count} clauses" if row.chunk_count else row.download_mode
                superseded = f" superseded_by={row.superseded_by}" if row.superseded_by else ""
                print(f"{mark} {row.priority} {row.doc_id:28} {extra:14} {row.title[:52]}{superseded}")
            print("\ntotals:", corpus_totals(db))
            return 0

        state_path = Path(settings.rag_regulatory_state_file)
        state = _load_state(state_path)
        files_state: dict = state.setdefault("files", {})

        ingested = skipped = failed = 0

        if args.direct_only:
            targets = [
                row
                for row in manifest.values()
                if row.can_auto_fetch and (not args.doc_id or row.doc_id == args.doc_id)
            ]
            if not targets:
                print("No manifest rows with download_mode=direct to fetch.")
                return 0
            for row in targets:
                if args.dry_run:
                    print(f"[dry-run] would download {row.doc_id} <- {row.direct_pdf_url}")
                    continue
                try:
                    result = fetch_direct(db, row.doc_id, force=args.force)
                except IngestError as exc:
                    print(f"FAIL {row.doc_id}: {exc}")
                    failed += 1
                    continue
                if result.skipped:
                    print(f"SKIP {row.doc_id}: {result.message}")
                    skipped += 1
                else:
                    print(f"OK   {row.doc_id}: {result.chunk_count} clauses / {result.page_count} pages")
                    ingested += 1
        else:
            staging_dir = Path(args.dir)
            files = _staged_files(staging_dir)
            if not files:
                print(
                    f"No documents found in {staging_dir}.\n"
                    "Download the official PDFs and name each after its manifest doc_id, "
                    "e.g. LEND-DLD-2025.pdf. Run with --list to see what is expected."
                )
                return 0

            for path in files:
                doc_id = _doc_id_for(path, set(manifest))
                if doc_id is None:
                    print(f"SKIP {path.name}: filename does not match any manifest doc_id")
                    skipped += 1
                    continue
                if args.doc_id and doc_id != args.doc_id:
                    continue

                digest = _file_sha256(path)
                prior = files_state.get(doc_id) or {}
                if not args.force and prior.get("sha256") == digest:
                    print(f"SKIP {doc_id}: unchanged ({path.name})")
                    skipped += 1
                    continue
                if args.dry_run:
                    print(f"[dry-run] would ingest {doc_id} <- {path.name}")
                    continue

                try:
                    result = ingest_document(
                        db,
                        doc_id=doc_id,
                        data=path.read_bytes(),
                        filename=path.name,
                        force=args.force,
                    )
                except IngestError as exc:
                    print(f"FAIL {doc_id}: {exc}")
                    failed += 1
                    continue

                files_state[doc_id] = {
                    "sha256": digest,
                    "filename": path.name,
                    "chunks": result.chunk_count,
                    "pages": result.page_count,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                print(f"OK   {doc_id}: {result.chunk_count} clauses / {result.page_count} pages")
                ingested += 1

        if not args.dry_run:
            superseded = apply_supersession(db)
            state["last_sync"] = datetime.now(timezone.utc).isoformat()
            _save_state(state_path, state)
            print(
                f"\ningested={ingested} skipped={skipped} failed={failed} "
                f"supersession_links={superseded}"
            )
            print("totals:", corpus_totals(db))
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
