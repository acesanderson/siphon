# Spec: Load PG-19 Non-Fiction Books into Siphon Eval Dataset

## Goal

Supplement a YouTube transcript eval dataset by loading long non-fiction books from
PG-19 (Project Gutenberg) into Siphon DB. Targets summarization eval bins that are
still underfilled after the YouTube transcript load.

## Context

The eval dataset uses `ProcessedContentORM` in the `siphon2` Postgres DB. Each record
is a long document binned by token count. The YouTube transcript loader already filled
bins 16 and 18; this script fills the remaining shortfall.

Token bins:
| Bin | Token range | Current count | Target | Need |
|-----|-------------|---------------|--------|------|
| 17  | 60K–81K     | 11            | 15     | 4    |
| 19  | 109K–148K   | 6             | 10     | 4    |
| 20  | 148K–200K   | 2             | 10     | 8    |

Bins 16 and 18 are already satisfied — skip them.

## Codebase orientation

- ORM model: `src/siphon_server/database/postgres/models.py` — `ProcessedContentORM`
- DB connection: `src/siphon_server/database/postgres/connection.py` — `SessionLocal`
- Token counter: `src/siphon_server/core/count_tokens.py` — check this for the right
  function to use (for consistency with the rest of the pipeline)
- Existing loader for reference: `dev/fetch_long_transcripts.py`
- Run with: `PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py`

## ORM field mapping

```python
ProcessedContentORM(
    uri=f"gutenberg:///{pg_id}",          # e.g. gutenberg:///12345
    source_type="Gutenberg",              # see note below on enum
    original_source=f"https://www.gutenberg.org/ebooks/{pg_id}",
    source_hash=None,
    content_text=book_text,               # full book text, no truncation
    content_metadata={
        "pg_id": pg_id,
        "title": title,
        "author": author,
        "subject": subject,               # LoC subject string from catalog
        "publication_date": pub_date,
        "token_count": token_count,
        "eval_bin": bin_num,
    },
    title=title,
    description=f"{author}. {subject}",
    summary="",
    topics=[],
    entities=[],
    tags=[f"eval-bin-{bin_num}", "pg19", "non-fiction"],
    created_at=int(time.time()),
    updated_at=int(time.time()),
    embedding=None,
    embed_model=None,
)
```

**Source type note**: `SourceType` enum in `siphon_api/enums.py` does not have a
`Gutenberg` value. Add `GUTENBERG = "Gutenberg"` to the enum before writing any
records. Also update `siphon_api/interfaces.py` if it references the enum exhaustively.
The `from_orm` converter does `SourceType(orm.source_type)` so it will break on load if
the enum value is missing. The enum file is at:
`../siphon-api/src/siphon_api/enums.py` (editable install).

## Data sources

**PG-19 dataset**: `deepmind/pg19` on HuggingFace. Fields: `id` (int, Gutenberg book
ID), `short_book_title`, `publication_date`, `url`, `book_text`. Load with
`streaming=True` to avoid downloading the full ~37GB corpus upfront.

**PG catalog** (for non-fiction filtering): Download the subjects CSV from Project
Gutenberg's catalog at `https://www.gutenberg.org/cache/epub/feeds/` — the file
`pg_catalog.csv` includes columns `Text#` (book ID), `Subjects`, `Authors`, `Title`.
Cache it locally in `/tmp/pg_catalog.csv`.

## Non-fiction filtering

Join PG-19 entries on `id` == `pg_catalog["Text#"]`. Keep books where `Subjects`
contains at least one of:

- History, Biography, Science, Technology, Philosophy, Economics, Geography,
  Sociology, Political science, Education, Medicine, Agriculture, Law

Drop books where `Subjects` contains: Fiction, Poetry, Drama, Music, "Juvenile",
"Short stories".

If a book has ambiguous subjects (e.g. "History -- Fiction"), drop it.

## Token counting

Use whatever token counter is in `siphon_server.core.count_tokens`. If it wraps
tiktoken or a HF tokenizer, use it directly on `book_text`. Token count determines
bin assignment — do not use word count or character proxies.

## Sampling logic

For each target bin, collect all qualifying books whose token count falls within the
bin range. Sample randomly (fixed seed for reproducibility). Load until the bin reaches
its target count, checking existing DB records first to avoid duplicates (query by
`source_type="Gutenberg"` and `tags @> ARRAY['eval-bin-N']`).

Load a few extras per bin (e.g. target + 3) in case some fail.

## Script interface

```
PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py
PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py --dry-run
PYTHONPATH=src .venv/bin/python -u dev/fetch_pg19_books.py --bin 20
```

Env vars required: `POSTGRES_PASSWORD`, `POSTGRES_USERNAME` (same as the rest of
Siphon). No API keys needed.

## Out of scope

- Embedding (the embed-batch pipeline handles this separately)
- Enrichment (title/description are populated from catalog metadata; summary/topics
  left empty for the pipeline to fill)
- Bin 20 may still come up short — PG-19 books >148K tokens are uncommon. If fewer
  than 10 qualify after filtering, note the actual count in output and do not pad with
  out-of-range books. The shortfall can be addressed later with a different source.
