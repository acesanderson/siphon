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


def _find_note(vault_root: Path, name: str) -> Path | None:
    """Search vault recursively for {name}.md (case-insensitive on the stem)."""
    target = name.lower() + ".md"
    for md in vault_root.rglob("*.md"):
        if md.name.lower() == target:
            return md
    return None


def _collect_notes(
    note_path: Path,
    vault_root: Path,
    visited: set[Path],
) -> list[tuple[str, str]]:
    """Recursively collect (title, content) for a note and all its wikilinked notes."""
    if note_path in visited:
        return []
    visited.add(note_path)

    try:
        content = note_path.read_text(encoding="utf-8")
    except OSError:
        return []

    title = note_path.stem
    results: list[tuple[str, str]] = [(title, content)]

    for m in _WIKILINK_RE.finditer(content):
        link_name = m.group(1).strip()
        linked_path = _find_note(vault_root, link_name)
        if linked_path and linked_path not in visited:
            results.extend(_collect_notes(linked_path, vault_root, visited))

    return results


class ObsidianExtractor(ExtractorStrategy):
    """Extract an Obsidian note and all its wikilinked notes recursively."""

    source_type: SourceType = SourceType.OBSIDIAN

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        note_path = Path(source.original_source).resolve()
        vault_root = _find_vault_root(note_path)

        visited: set[Path] = set()
        notes = _collect_notes(note_path, vault_root, visited)

        sections: list[str] = []
        for title, content in notes:
            sections.append(f"# {title}\n\n{content}")

        combined = "\n\n---\n\n".join(sections)
        metadata = {
            "root_note": str(note_path),
            "vault_root": str(vault_root),
            "note_count": len(notes),
        }
        return ContentData(
            source_type=self.source_type,
            text=combined,
            metadata=metadata,
        )
