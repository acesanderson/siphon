from __future__ import annotations

import hashlib
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo
from siphon_server.sources.obsidian.text_utils import read_note


def _find_vault_root(note_path: Path) -> Path | None:
    """Walk up directories from note_path until a dir containing .obsidian/ is found."""
    current = note_path.parent
    while True:
        if (current / ".obsidian").is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


class ObsidianParser(ParserStrategy):
    """Parse Obsidian notes: .md files inside a vault (identified by .obsidian/ directory)."""

    source_type: SourceType = SourceType.OBSIDIAN

    @override
    def can_handle(self, source: str) -> bool:
        try:
            p = Path(source).resolve()
            if not p.exists() or p.suffix.lower() != ".md":
                return False
            return _find_vault_root(p) is not None
        except (TypeError, OSError):
            return False

    @override
    def parse(self, source: str) -> SourceInfo:
        p = Path(source).resolve()
        stem = p.stem
        full_text, _, _ = read_note(p)
        content_hash = hashlib.sha256(full_text.encode("utf-8", errors="replace")).hexdigest()
        return SourceInfo(
            source_type=self.source_type,
            uri=f"obsidian:///{stem}",
            original_source=source,
            hash=content_hash,
        )
