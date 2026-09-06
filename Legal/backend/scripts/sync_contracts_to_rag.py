#!/usr/bin/env python3
"""Upload executed contracts (PDF/DOCX) to the Vertex AI RAG corpus.

Mirrors ``sync_templates_to_rag.py`` for the local ``contracts/`` folder
(and GCS prefix ``legalos/contracts``).

Tracks uploads in ``config/.rag_contracts_upload_state.json`` (gitignored).

Usage:
    python backend/scripts/sync_contracts_to_rag.py
    python backend/scripts/sync_contracts_to_rag.py --dry-run
    python backend/scripts/sync_contracts_to_rag.py --force
    python backend/scripts/sync_contracts_to_rag.py --contracts-dir /tmp/contracts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED = {".docx", ".pdf", ".txt"}


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


def _agent_client(project: str, location: str, creds_file: str):
    import agentplatform
    from google.oauth2 import service_account

    on_gcp = bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))
    if creds_file and os.path.isfile(creds_file) and not on_gcp:
        creds = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return agentplatform.Client(
            project=project, location=location, credentials=creds
        )
    return agentplatform.Client(project=project, location=location)


def _candidates(contracts_dir: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(contracts_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _ALLOWED:
            continue
        if path.stat().st_size <= 0:
            continue
        out.append(path)
    return out


def main() -> int:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    parser = argparse.ArgumentParser(
        description="Sync contracts/*.(pdf|docx|txt) to Vertex RAG corpus."
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=Path(settings.contracts_dir),
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(settings.rag_contracts_upload_state_file),
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would upload")
    parser.add_argument("--force", action="store_true", help="Re-upload all files")
    args = parser.parse_args()

    corpus = settings.vertex_rag_corpus_resource
    if not corpus:
        print("[error] VERTEX_RAG_CORPUS_ID not configured", file=sys.stderr)
        return 1

    contracts_dir: Path = args.contracts_dir
    if not contracts_dir.is_dir():
        print(f"[error] contracts dir not found: {contracts_dir}", file=sys.stderr)
        return 1

    state_path: Path = args.state_file
    state = _load_state(state_path)
    files_state: dict = state.setdefault("files", {})

    candidates = _candidates(contracts_dir)
    if not candidates:
        print("[warn] no non-empty PDF/DOCX/TXT files found")
        return 0

    to_upload: list[Path] = []
    for path in candidates:
        digest = _file_sha256(path)
        prev = files_state.get(path.name, {})
        if args.force or prev.get("sha256") != digest:
            to_upload.append(path)

    print(f"[info] corpus: {corpus}")
    print(
        f"[info] contracts: {contracts_dir} "
        f"({len(candidates)} files, {len(to_upload)} to upload)"
    )

    if args.dry_run:
        for path in to_upload:
            print(f"  would upload: {path.name}")
        return 0

    if not to_upload:
        print("[done] all contracts already synced")
        return 0

    client = _agent_client(
        settings.gcp_project_id,
        settings.vertex_rag_location,
        settings.gcp_service_account_file,
    )

    uploaded = 0
    for path in to_upload:
        display = f"executed:{path.stem[:110]}"
        try:
            client.rag.upload_file(
                corpus_name=corpus,
                path=str(path),
                display_name=display,
            )
            files_state[path.name] = {
                "sha256": _file_sha256(path),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "kind": "executed",
            }
            uploaded += 1
            print(f"[ok]   uploaded {path.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[fail] {path.name}: {exc}", file=sys.stderr)

    state["corpus"] = corpus
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    _save_state(state_path, state)
    print(f"[done] uploaded {uploaded}/{len(to_upload)} file(s); state → {state_path}")
    return 0 if uploaded == len(to_upload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
