from __future__ import annotations

import re
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _find_vault_root(note_path: Path) -> Path:
    current = note_path.parent
    while True:
        if (current / ".obsidian").is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise ValueError(f"No Obsidian vault found above {note_path}")
        current = parent


class ObsidianExtractor(ExtractorStrategy):
    """Extract a single Obsidian note; wikilinks stored as URI list in metadata."""

    source_type: SourceType = SourceType.OBSIDIAN

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        note_path = Path(source.original_source).resolve()
        vault_root = _find_vault_root(note_path)

        try:
            text = note_path.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"Cannot read note: {note_path}") from e

        wikilinks = [
            f"obsidian:///{m.group(1).strip()}"
            for m in _WIKILINK_RE.finditer(text)
        ]

        metadata = {
            "note_path": str(note_path),
            "vault_root": str(vault_root),
            "wikilinks": wikilinks,
        }
        return ContentData(
            source_type=self.source_type,
            text=text,
            metadata=metadata,
        )
