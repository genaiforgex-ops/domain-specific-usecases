from pathlib import Path

from app.core.config import get_settings


class LocalStorageAdapter:
    def __init__(self):
        settings = get_settings()
        self.base_path = Path(settings.local_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        path = self.base_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def download(self, key: str) -> bytes:
        return (self.base_path / key).read_bytes()

    async def get_url(self, key: str) -> str:
        return str(self.base_path / key)
