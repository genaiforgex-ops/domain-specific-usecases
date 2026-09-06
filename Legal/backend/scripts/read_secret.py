#!/usr/bin/env python3
"""Standalone Secret Manager reader — isolates auth/secret access from the app.

Usage (from repo root or anywhere):
    python backend/scripts/read_secret.py
    python backend/scripts/read_secret.py --secret legalos
    python backend/scripts/read_secret.py --project agentic-ai-476106 --secret legalos
    python backend/scripts/read_secret.py --sa /path/to/service_account.json

Auth resolution order:
    1. --sa / GCP_SERVICE_ACCOUNT_FILE  -> service-account key file
    2. GOOGLE_APPLICATION_CREDENTIALS   -> key file (the SDK's standard var)
    3. Application Default Credentials   -> gcloud / Workload Identity
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Default to the key file checked into the repo root (gitignored).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SA = REPO_ROOT / "service_account_agentic_uat.json"


def build_client(sa_file: str):
    from google.cloud import secretmanager

    if sa_file and os.path.isfile(sa_file):
        print(f"[auth] using service-account key file: {sa_file}")
        return secretmanager.SecretManagerServiceClient.from_service_account_file(sa_file)

    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print(f"[auth] using GOOGLE_APPLICATION_CREDENTIALS={os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
    else:
        print("[auth] using Application Default Credentials (gcloud / Workload Identity)")
    return secretmanager.SecretManagerServiceClient()


def resolve_project(explicit: str, sa_file: str) -> str:
    if explicit:
        return explicit
    # Pull project_id straight out of the key file if we have one.
    if sa_file and os.path.isfile(sa_file):
        import json

        with open(sa_file) as fh:
            pid = json.load(fh).get("project_id")
        if pid:
            return pid
    import google.auth

    _, pid = google.auth.default()
    return pid or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Read a secret from GCP Secret Manager.")
    parser.add_argument("--project", default=os.getenv("GCP_PROJECT_ID", ""), help="GCP project id")
    parser.add_argument(
        "--secret",
        default=os.getenv("GCP_SECRET_NAME") or "",
        help="secret id (defaults from LEGALOS_ENV: legalos_dev / legalos_uat / legalos_prod)",
    )
    parser.add_argument("--version", default="latest", help="secret version (default: latest)")
    parser.add_argument(
        "--sa",
        default=os.getenv("GCP_SERVICE_ACCOUNT_FILE", str(DEFAULT_SA)),
        help="service-account key file (default: repo-root key or env)",
    )
    parser.add_argument("--show", action="store_true", help="print the raw secret payload")
    args = parser.parse_args()

    secret_id = args.secret.strip()
    if not secret_id:
        env_key = os.getenv("LEGALOS_ENV", "dev").strip().lower()
        secret_by_env = {
            "dev": "legalos_dev",
            "uat": "legalos_uat",
            "prod": "legalos_prod",
            "production": "legalos_prod",
            "preprod": "legalos_uat",
        }
        secret_id = secret_by_env.get(env_key, f"legalos_{env_key}" if env_key else "legalos_dev")

    sa_file = args.sa if os.path.isfile(args.sa) else ""

    try:
        client = build_client(sa_file)
        project = resolve_project(args.project, sa_file)
        if not project:
            print("[error] could not resolve a project id; pass --project", file=sys.stderr)
            return 2

        name = f"projects/{project}/secrets/{secret_id}/versions/{args.version}"
        print(f"[read]  {name}")
        resp = client.access_secret_version(request={"name": name})
        payload = resp.payload.data.decode("utf-8")

        print(f"[ok]    fetched secret '{secret_id}' ({len(payload)} bytes)")
        if args.show:
            print("-" * 40)
            print(payload)
            print("-" * 40)
        else:
            print("[hint]  pass --show to print the payload")
        return 0
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"[FAIL]  {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
