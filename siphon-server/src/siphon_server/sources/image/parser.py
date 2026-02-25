from __future__ import annotations

import hashlib
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.file_types import EXTENSIONS
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo

_IMAGE_EXTS = set(EXTENSIONS["Image"])


class ImageParser(ParserStrategy):
    """Parse image sources: local file paths or image URLs."""

    source_type: SourceType = SourceType.IMAGE

    @override
    def can_handle(self, source: str) -> bool:
        lower = source.lower()
        # File path
        try:
            p = Path(source)
            if p.exists() and p.suffix.lower() in _IMAGE_EXTS:
                return True
        except (TypeError, OSError):
            pass
        # URL ending in image extension
        if lower.startswith("http://") or lower.startswith("https://"):
            for ext in _IMAGE_EXTS:
                if lower.split("?")[0].endswith(ext):
                    return True
        return False

    @override
    def parse(self, source: str) -> SourceInfo:
        p = Path(source)
        if p.exists():
            ext = p.suffix.lower().lstrip(".")
            h = self._hash_file(p)
        else:
            ext = Path(source.split("?")[0]).suffix.lower().lstrip(".")
            h = hashlib.sha256(source.encode()).hexdigest()[:16]
        uri = f"image:///{ext}/{h}"
        return SourceInfo(
            source_type=self.source_type,
            uri=uri,
            original_source=source,
            hash=h,
        )

    def _hash_file(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
