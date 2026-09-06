import asyncio

from google.cloud import storage

from app.core.config import get_settings


class GCSStorageAdapter:
    """Google Cloud Storage backend. Credentials resolve via Application
    Default Credentials — no access keys in config. The bucket is set by
    `gcs_bucket`; callers namespace keys by environment to keep env
    uploads separate in a shared bucket. Blob calls are sync in the google
    client, so they run in a thread to avoid blocking the event loop."""

    def __init__(self):
        settings = get_settings()
        self.bucket_name = settings.gcs_bucket
        self._client = storage.Client()
        self._bucket = self._client.bucket(self.bucket_name)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        def _put() -> None:
            blob = self._bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)

        await asyncio.to_thread(_put)
        return key

    async def download(self, key: str) -> bytes:
        return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)

    async def get_url(self, key: str) -> str:
        return f"gs://{self.bucket_name}/{key}"
