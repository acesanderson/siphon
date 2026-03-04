from __future__ import annotations

import re
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---[ \t]*\n.*?\n---[ \t]*\n?", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body) for an Obsidian note.

    frontmatter is the raw YAML block including delimiters, or "" if absent.
    body is everything after the frontmatter block, stripped of leading whitespace.
    If no frontmatter is present, frontmatter="" and body=full text.
    """
    m = _FRONTMATTER_RE.match(text)
    if m:
        return m.group(0), text[m.end():].lstrip("\n")
    return "", text


def read_note(path: Path) -> tuple[str, str, str]:
    """Read an Obsidian note and return (full_text, frontmatter, body).

    full_text: raw file contents (used for Gate 1 hash and content_text storage)
    frontmatter: YAML block or ""
    body: note content after frontmatter (used for Gate 2 significance)
    """
    full_text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = split_frontmatter(full_text)
    return full_text, frontmatter, body
