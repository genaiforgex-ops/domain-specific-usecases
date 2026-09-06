#!/usr/bin/env python3
"""Migrate legacy local MSA blobs into GCS and rewrite DB storage_keys.

Before DOCUMENT_STORAGE_BACKEND=gcs, uploads lived under LOCAL_STORAGE_PATH
with bare keys like ``{uuid}.pdf``. New uploads use
``{MSA_DOCUMENTS_PREFIX}/{uuid}.ext`` in gs://{LEGAL_TEMPLATES_BUCKET}/.

This script:
  1. Finds msa_document_versions.storage_key values without a ``/``
  2. Reads the file from LOCAL_STORAGE_PATH (if present)
  3. Uploads to gs://…/{prefix}/{same-filename}
  4. Updates the DB row to the prefixed key

Usage (from repo, with backend env):
    docker compose exec backend python scripts/migrate_local_msa_to_gcs.py --dry-run
    docker compose exec backend python scripts/migrate_local_msa_to_gcs.py
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(BACKEND_ROOT))
    from sqlalchemy import select

    from app.config import settings
    from app.database import SessionLocal
    from app.models.msa_version import MSADocumentVersion
    from app.services.document_storage import _gcs_client, get_document_storage

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would migrate without writing GCS/DB",
    )
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=None,
        help="Override LOCAL_STORAGE_PATH",
    )
    args = parser.parse_args()

    storage = get_document_storage()
    if type(storage).__name__ != "GcsDocumentStorage":
        print(
            f"[error] DOCUMENT_STORAGE_BACKEND must be gcs (got {type(storage).__name__})",
            file=sys.stderr,
        )
        return 1

    local_dir = args.local_dir or Path(settings.local_storage_path)
    prefix = storage.prefix
    bucket_name = storage.bucket_name
    bucket = _gcs_client().bucket(bucket_name)

    db = SessionLocal()
    rows = db.execute(
        select(MSADocumentVersion).where(
            MSADocumentVersion.storage_key.isnot(None),
            ~MSADocumentVersion.storage_key.like("%/%"),
        )
    ).scalars().all()

    print(f"[info] bare storage_keys: {len(rows)}")
    print(f"[info] local_dir={local_dir} → gs://{bucket_name}/{prefix}/")

    ok = skipped = missing = failed = 0
    for row in rows:
        bare = (row.storage_key or "").lstrip("/")
        new_key = f"{prefix}/{bare}" if prefix else bare
        local_path = local_dir / bare
        dest = f"gs://{bucket_name}/{new_key}"

        if not local_path.is_file():
            # Already in GCS under prefix? just rewrite DB.
            if bucket.blob(new_key).exists():
                print(f"[rewrite] id={row.id} {bare} → {new_key} (already in GCS)")
                if not args.dry_run:
                    row.storage_key = new_key
                ok += 1
                continue
            print(f"[missing] id={row.id} {bare} (not on disk, not in GCS)")
            missing += 1
            continue

        if bucket.blob(new_key).exists():
            print(f"[skip-upload] id={row.id} already at {dest}; rewriting DB key")
            if not args.dry_run:
                row.storage_key = new_key
            skipped += 1
            continue

        mime = row.mime_type or mimetypes.guess_type(bare)[0] or "application/octet-stream"
        size = local_path.stat().st_size
        print(f"[upload] id={row.id} {local_path.name} ({size} bytes) → {dest}")
        if args.dry_run:
            ok += 1
            continue
        try:
            data = local_path.read_bytes()
            blob = bucket.blob(new_key)
            blob.upload_from_string(data, content_type=mime)
            row.storage_key = new_key
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[fail] id={row.id} {bare}: {exc}", file=sys.stderr)
            failed += 1

    if not args.dry_run:
        db.commit()
    else:
        db.rollback()
    db.close()

    print(
        f"[done] uploaded/rewrote={ok} skipped={skipped} "
        f"missing={missing} failed={failed} dry_run={args.dry_run}"
    )
    return 1 if failed or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
