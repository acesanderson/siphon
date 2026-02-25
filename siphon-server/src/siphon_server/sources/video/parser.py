from __future__ import annotations

import hashlib
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.file_types import EXTENSIONS
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo

_VIDEO_EXTS = set(EXTENSIONS["Video"])
_YOUTUBE_DOMAINS = {"youtube.com", "youtu.be"}


class VideoParser(ParserStrategy):
    """Parse local video file sources. YouTube URLs are excluded."""

    source_type: SourceType = SourceType.VIDEO

    @override
    def can_handle(self, source: str) -> bool:
        if any(d in source for d in _YOUTUBE_DOMAINS):
            return False
        try:
            p = Path(source)
            return p.exists() and p.suffix.lower() in _VIDEO_EXTS
        except (TypeError, OSError):
            return False

    @override
    def parse(self, source: str) -> SourceInfo:
        path = Path(source)
        assert path.exists(), f"File does not exist: {source}"
        ext = path.suffix.lower().lstrip(".")
        h = self._hash_file(path)
        return SourceInfo(
            source_type=self.source_type,
            uri=f"video:///{ext}/{h}",
            original_source=source,
            hash=h,
        )

    def _hash_file(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
