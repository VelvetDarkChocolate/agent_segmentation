import shutil
from pathlib import Path

from backend.core.config import settings


class LocalObjectStore:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.object_store_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, object_key: str, data: bytes) -> str:
        target = self.root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return object_key

    def save_file(self, object_key: str, source_path: Path) -> str:
        target = self.root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        return object_key

    def path_for(self, object_key: str) -> Path:
        return self.root / object_key

    def url_for(self, object_key: str) -> str:
        return f"/objects/{object_key}"


object_store = LocalObjectStore()

