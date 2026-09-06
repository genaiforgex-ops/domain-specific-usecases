"""Document blob storage for MSA negotiation files (uploads + OnlyOffice saves).

Backends:
  - ``local`` — filesystem under LOCAL_STORAGE_PATH (lost if volume/pod is wiped)
  - ``gcs``   — durable objects in
    gs://{LEGAL_TEMPLATES_BUCKET}/{MSA_DOCUMENTS_PREFIX}/…
    (default prefix: ``legal_live_docs``)

OnlyOffice still reads/writes through the LegalOS API; the backend persists
bytes via this module either way.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger("legalos.storage")


class DocumentStorage(ABC):
    @abstractmethod
    def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        """Returns (storage_key, sha256_hex)."""

    @abstractmethod
    def download(self, storage_key: str) -> bytes:
        ...

    @abstractmethod
    def presigned_url(self, storage_key: str, expires_seconds: int = 3600) -> str:
        ...


class LocalDocumentStorage(DocumentStorage):
    def __init__(self, base_path: str) -> None:
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        return self.base / storage_key

    def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        ext = Path(filename).suffix or ".bin"
        key = f"{uuid.uuid4().hex}{ext}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key, sha

    def download(self, storage_key: str) -> bytes:
        return self._path(storage_key).read_bytes()

    def presigned_url(self, storage_key: str, expires_seconds: int = 3600) -> str:
        return f"/api/msa/files/{storage_key}"


def _on_gcp() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))


@lru_cache(maxsize=1)
def _gcs_client():
    from google.cloud import storage
    from google.oauth2 import service_account

    creds_file = (settings.gcp_service_account_file or "").strip()
    if creds_file and os.path.isfile(creds_file) and not _on_gcp():
        creds = service_account.Credentials.from_service_account_file(creds_file)
        return storage.Client(project=settings.gcp_project_id or None, credentials=creds)
    return storage.Client(project=settings.gcp_project_id or None)


class GcsDocumentStorage(DocumentStorage):
    """Durable MSA blobs in the shared LegalOS GCS bucket."""

    def __init__(self, bucket_name: str, prefix: str) -> None:
        self.bucket_name = bucket_name.strip()
        self.prefix = (prefix or "msa").strip().strip("/")
        if not self.bucket_name:
            raise ValueError("GCS document storage requires LEGAL_TEMPLATES_BUCKET")

    def _candidate_object_names(self, storage_key: str) -> list[str]:
        """Resolve DB storage_key → possible GCS object names.

        New uploads store ``{prefix}/{uuid}.ext``. Legacy local-era rows store a
        bare ``{uuid}.ext``; try both the bare key and ``{prefix}/{bare}``.
        """
        key = (storage_key or "").lstrip("/")
        if not key:
            return []
        names = [key]
        if self.prefix and "/" not in key:
            prefixed = f"{self.prefix}/{key}"
            if prefixed not in names:
                names.append(prefixed)
        return names

    def _new_key(self, filename: str) -> str:
        ext = Path(filename).suffix or ".bin"
        name = f"{uuid.uuid4().hex}{ext}"
        return f"{self.prefix}/{name}" if self.prefix else name

    def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        key = self._new_key(filename)
        blob = _gcs_client().bucket(self.bucket_name).blob(key)
        blob.upload_from_string(data, content_type=content_type or "application/octet-stream")
        logger.info("Uploaded MSA blob gs://%s/%s (%d bytes)", self.bucket_name, key, len(data))
        return key, sha

    def download(self, storage_key: str) -> bytes:
        bucket = _gcs_client().bucket(self.bucket_name)
        tried: list[str] = []
        for key in self._candidate_object_names(storage_key):
            tried.append(f"gs://{self.bucket_name}/{key}")
            blob = bucket.blob(key)
            if blob.exists():
                return blob.download_as_bytes()

        # Transition: blobs uploaded under DOCUMENT_STORAGE_BACKEND=local may
        # still sit on LOCAL_STORAGE_PATH (Docker volume) until migrated to GCS.
        local_key = (storage_key or "").lstrip("/")
        if local_key and "/" not in local_key:
            local_path = Path(settings.local_storage_path) / local_key
            if local_path.is_file():
                logger.warning(
                    "Serving MSA blob from local fallback %s (not yet in GCS)",
                    local_path,
                )
                return local_path.read_bytes()

        raise FileNotFoundError(
            "GCS object not found: " + (", ".join(tried) if tried else storage_key)
        )

    def presigned_url(self, storage_key: str, expires_seconds: int = 3600) -> str:
        # Serve via LegalOS (auth + OnlyOffice token download). Do not expose
        # raw GCS signed URLs to the browser.
        return f"/api/msa/files/{storage_key}"


_storage: DocumentStorage | None = None
_regulatory_storage: DocumentStorage | None = None


def get_regulatory_storage() -> DocumentStorage:
    """Storage for ingested regulatory originals (statutes, master directions).

    Same backends as `get_document_storage`, but under its own GCS prefix so the
    corpus originals stay separate from MSA working documents.
    """
    global _regulatory_storage
    if _regulatory_storage is None:
        backend = (settings.document_storage_backend or "local").strip().lower()
        if backend == "gcs":
            bucket = (settings.legal_templates_bucket or "").strip()
            prefix = (settings.regulatory_documents_prefix or "regulatory").strip().strip("/")
            _regulatory_storage = GcsDocumentStorage(bucket, prefix)
            logger.info(
                "Regulatory storage backend=gcs bucket=%s prefix=%s/", bucket, prefix
            )
        else:
            _regulatory_storage = LocalDocumentStorage(settings.local_storage_path)
            logger.info(
                "Regulatory storage backend=local path=%s", settings.local_storage_path
            )
    return _regulatory_storage


def get_document_storage() -> DocumentStorage:
    global _storage
    if _storage is None:
        backend = (settings.document_storage_backend or "local").strip().lower()
        if backend == "gcs":
            bucket = (settings.legal_templates_bucket or "").strip()
            prefix = (settings.msa_documents_prefix or "legal_live_docs").strip().strip("/")
            _storage = GcsDocumentStorage(bucket, prefix)
            logger.info(
                "Document storage backend=gcs bucket=%s prefix=%s/",
                bucket,
                prefix,
            )
        else:
            _storage = LocalDocumentStorage(settings.local_storage_path)
            logger.info(
                "Document storage backend=local path=%s",
                settings.local_storage_path,
            )
    return _storage
