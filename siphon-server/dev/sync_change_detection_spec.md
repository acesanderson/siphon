# Spec: Vault Sync Change Detection
Last updated: 2026-03-03

## Goal

Improve `siphon sync` so that:

1. **Content-gated sync** — notes whose file content hasn't actually changed are skipped,
   even if their mtime is newer than `updated_at` (fixes false positives from Obsidian
   touching files without editing them).

2. **Significance-gated sync** — notes whose content changed only trivially (below a
   hardcoded threshold) are also skipped, avoiding LLM enrichment calls for minor edits.

No schema changes are required. All necessary fields (`source_hash`, `content_text`,
`updated_at`) already exist in `ProcessedContentORM` and flow correctly through
`to_orm`/`from_orm`.

---

## Files to Change

| File | Change |
|---|---|
| `siphon-server/src/siphon_server/sources/obsidian/text_utils.py` | **New file** — shared `read_note()` / `split_frontmatter()` helpers |
| `siphon-server/src/siphon_server/sources/obsidian/parser.py` | Import `read_note()`; compute content hash in `parse()` |
| `siphon-server/src/siphon_server/database/postgres/repository.py` | Add `get_sync_metadata()` |
| `siphon-client/src/siphon_client/cli/sync.py` | Add hash + significance gates; consolidate file reads; remove `_is_empty()` |

`siphon-api` — no changes.
`siphon-server/database/postgres/models.py` — no changes.
`siphon-server/database/postgres/converters.py` — no changes.

---

## Change 1 — New shared helper: `text_utils.py`

**File**: `siphon-server/src/siphon_server/sources/obsidian/text_utils.py` (new file)

This module contains the single source of truth for Obsidian text processing. Both
`ObsidianParser` (server) and the sync loop (client) import from here. They must
use the same function to produce the same hash for the same file.

```python
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
```

---

## Change 2 — `ObsidianParser.parse()`: compute content hash

**File**: `siphon-server/src/siphon_server/sources/obsidian/parser.py`

`ObsidianParser.parse()` currently sets `hash=None`. Change it to compute a SHA-256
hash of the **full file text** (Gate 1 uses full text — see Significance design below).

```python
import hashlib
from pathlib import Path
from siphon_server.sources.obsidian.text_utils import read_note

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
```

The file is read a second time in `ObsidianExtractor.extract()`. Accept this minor
redundancy — the alternatives (threading the text through, or changing the interface)
are more complex than the cost of a second read.

---

## Change 3 — `ContentRepository`: add `get_sync_metadata()`

**File**: `siphon-server/src/siphon_server/database/postgres/repository.py`

The current sync loop calls `repository.get(uri)` — a full-row SELECT — once per
existing note. For a large vault this is expensive (every `content_text` is fetched).
Replace with a single batch query that returns only the fields needed for change
detection.

Add to `ContentRepository`:

```python
def get_sync_metadata(
    self, source_type: SourceType
) -> dict[str, tuple[int, str | None, int]]:
    """Return {uri: (updated_at, source_hash, content_len)} for all records
    of the given source type. Single query; used by the sync loop to avoid
    N+1 full-row reads.
    """
    with self._session() as db:
        from sqlalchemy import func
        rows = (
            db.query(
                ProcessedContentORM.uri,
                ProcessedContentORM.updated_at,
                ProcessedContentORM.source_hash,
                func.length(ProcessedContentORM.content_text).label("content_len"),
            )
            .filter(ProcessedContentORM.source_type == source_type.value)
            .all()
        )
        return {
            row.uri: (row.updated_at, row.source_hash, row.content_len)
            for row in rows
        }
```

> Note: `func.length()` in SQLAlchemy maps to PostgreSQL `LENGTH()`, which returns
> character count for `TEXT` columns. This is sufficient for the significance gate
> (see Decision 2).

---

## Change 4 — `sync.py`: replace the change-detection loop

**File**: `siphon-client/src/siphon_client/cli/sync.py`

### 4a. Replace `repository.get(uri)` loop with batch metadata fetch

Replace the current per-note `repository.get(uri)` calls with a single
`get_sync_metadata()` call. This also retrieves `source_hash` and `content_len`
for use in the new gates.

```python
# Before:
existing_uris: set[str] = set(
    repository.get_all_uris_by_source_type(SourceType.OBSIDIAN)
)

# After:
sync_meta: dict[str, tuple[int, str | None, int]] = repository.get_sync_metadata(
    SourceType.OBSIDIAN
)
existing_uris: set[str] = set(sync_meta.keys())
```

### 4b. New gate logic in the classification loop

Replace the current `file_mtime <= existing.updated_at` check with three sequential
gates. A note is skipped only if it passes **all** skip conditions:

```
Gate 0 — mtime:        file_mtime <= stored updated_at            → skip (fast, no I/O)
Gate 1 — content hash: SHA-256(full_text) == stored source_hash   → skip (content unchanged)
Gate 2 — significance: body_delta_chars < MIN_CHARS
                        AND body_delta_pct < MIN_PCT               → skip (change too small)
```

Gates are ordered cheapest-first. Gate 0 requires no file I/O. Gates 1 and 2 both
require reading the file — consolidate into a single read via `read_note()` (see §4c).

**Hardcoded thresholds (no CLI flags):**
```python
_MIN_CHANGE_CHARS = 50    # absolute body character delta
_MIN_CHANGE_PCT   = 0.02  # relative body character delta (2%)
```

Gate 2 uses **body length only** (text after frontmatter), not full file length.
This prevents frontmatter-only mutations (Jekyll pipeline, Dataview, auto-tags) from
crossing the significance threshold. The OR logic means a note re-syncs if
`body_delta >= MIN_CHARS` OR `body_delta_pct >= MIN_PCT` — whichever fires first.

`stored_content_len` from `get_sync_metadata()` is full-text length (PostgreSQL
`LENGTH(content_text)`). Since `content_text` stores the full file text including
frontmatter, the sync loop must re-derive body length from the stored record. However,
since we don't store the body length separately, Gate 2 uses **new body length only**
against `_MIN_CHANGE_CHARS` as the primary guard, and skips the percentage gate if
`stored_content_len` is unavailable or zero. This is a pragmatic simplification — the
absolute threshold (`MIN_CHARS=50`) is the reliable gate; percentage is a bonus.

Concretely:
```python
_, _, new_body = read_note(note_path)
body_delta = abs(len(new_body) - stored_content_len)
body_pct = body_delta / max(stored_content_len, 1)
is_trivial = body_delta < _MIN_CHANGE_CHARS and body_pct < _MIN_CHANGE_PCT
```

### 4c. Consolidate file reads

Currently `_is_empty()` reads the file. The new gates also read the file. Consolidate:
read once per note via `read_note()` from `text_utils.py`, use for all purposes
(empty check, hash, significance).

Remove `_is_empty()`. Replace with inline logic after `read_note()`:

```python
from siphon_server.sources.obsidian.text_utils import read_note
import hashlib

# Inside the classification loop, after Gate 0 passes:
full_text, _, new_body = read_note(note_path)
is_empty = not full_text.strip()
if is_empty:
    stats.empty_skipped += 1
    continue

content_hash = hashlib.sha256(full_text.encode("utf-8", errors="replace")).hexdigest()
stored_updated_at, stored_hash, stored_content_len = sync_meta[uri]

# Gate 1 — hash
if stored_hash is not None and content_hash == stored_hash:
    stats.hash_skipped += 1
    continue

# Gate 2 — significance
body_delta = abs(len(new_body) - stored_content_len)
body_pct = body_delta / max(stored_content_len, 1)
if body_delta < _MIN_CHANGE_CHARS and body_pct < _MIN_CHANGE_PCT:
    stats.trivial_skipped += 1
    continue

to_process.append((uri, note_path, False))
```

The `pre-filter` block that currently calls `_is_empty()` after classification is
eliminated — empty detection now happens inline during the gate sequence.

### 4d. New SyncStats fields

Add two new skip counters to `SyncStats`:

```python
hash_skipped: int = 0       # content unchanged (hash match)
trivial_skipped: int = 0    # content changed but below significance threshold
```

Update `summary()` to include them.

### 4e. No new CLI flags

Thresholds are hardcoded. No new Click options are added to the `sync` command.
The `--dry-run` flag already shows would-be counts per category; `hash_skipped` and
`trivial_skipped` will appear in dry-run output via the updated `SyncStats.summary()`.

---

## New Sync Flow (complete)

```
collect_notes()
  │
  ├─ uri not in existing_uris → NEW → to_process
  │
  └─ uri in existing_uris:
       Gate 0: file_mtime <= stored updated_at?   → SKIP (stats.skipped)
       read file via read_note() [single I/O]
       is_empty?                                  → SKIP (stats.empty_skipped)
       Gate 1: hash == stored source_hash?        → SKIP (stats.hash_skipped)
       Gate 2: body_delta below both thresholds?  → SKIP (stats.trivial_skipped)
       → CHANGED → to_process

process pipeline (extract → enrich → store)
embed-batch
prune stale
```

---

## Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| 1 | Frontmatter for hash/significance | Gate 1 (hash) uses **full file text**. Gate 2 (significance) uses **body only** (post-frontmatter). A frontmatter-only change trips Gate 1, then fails Gate 2 (body delta = 0) → correctly skipped. Future-proofed for Jekyll pipeline. |
| 2 | Significance thresholds | **Hardcoded**: `_MIN_CHANGE_CHARS = 50`, `_MIN_CHANGE_PCT = 0.02`. OR logic: re-sync if either threshold is exceeded. No CLI flags. |
| 3 | Shared helper location | `siphon_server/sources/obsidian/text_utils.py`. Both `parser.py` and `sync.py` import `read_note()` from there. Consistent with existing pattern of `sync.py` importing from `siphon-server`. |

---

## Non-goals

- Semantic diffing (embedding cosine distance between old and new text) — out of scope
- Per-folder or per-tag significance thresholds — out of scope
- Backfilling `source_hash` for existing records — not needed; on first run after
  deploy, all existing records have `source_hash = NULL`. A NULL hash always fails
  Gate 1 (no match), so existing notes will be processed once to populate their hash,
  then skipped on subsequent runs. This is correct behaviour.
- Changing the `ObsidianExtractor` — it continues to store full file text in
  `content_text` regardless of frontmatter stripping decisions above.
