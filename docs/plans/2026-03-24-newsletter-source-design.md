# Newsletter Source Design

**Date:** 2026-03-24
**Status:** Draft — pending Stalwart DevOps setup on nimzo before implementation

---

## 1. Goal

Add `newsletter` as a passive (mollusk) source type that periodically fetches emails from a dedicated newsletter inbox via JMAP, converts HTML bodies to markdown, and ingests them through the standard siphon pipeline. The ingestion account lives on a self-hosted Stalwart server (nimzo VPS); no third-party email provider is required.

---

## 2. Constraints and Non-Goals

**Constraints:**
- Must satisfy the registry contract: `parser.py`, `extractor.py`, `enricher.py` each containing exactly one class named `Newsletter*`, matching the directory name `newsletter`.
- `SourceType.NEWSLETTER` must be added to `siphon_api/enums.py`.
- Credentials are provided exclusively via environment variables — no hardcoded values, no config file reads.
- The extractor must use readabilipy + markdownify for HTML→markdown conversion, matching the ArticleExtractor approach.
- Checkpoint state is inferred entirely from the existing content table — no new tables or files.
- Sync is append-only. No automated pruning.
- JMAP is the protocol. IMAP is not used.

**Non-Goals:**
- Outbound email / sending of any kind.
- Multi-account support (one inbox only).
- Newsletter de-duplication across publications (same content from two senders is two records).
- Per-item splitting of roundup newsletters.
- Attachment handling of any kind.
- Automatic pruning when messages are deleted from the inbox.
- Webhook / push delivery — poll only.
- Provider portability beyond JMAP (no IMAP fallback).
- Any UI or web interface.

---

## 3. Interface Contracts

### 3.1 Environment Variables

```
NEWSLETTER_JMAP_URL       # JMAP session URL, e.g. https://mail.nimzo.example.com/.well-known/jmap
NEWSLETTER_JMAP_USER      # Email address of the newsletter inbox account
NEWSLETTER_JMAP_PASSWORD  # App password for the newsletter inbox account
NEWSLETTER_JMAP_PORT      # Optional, default 443
```

### 3.2 URI Scheme

```
newsletter:///<sender_domain>/<jmap_message_id>
```

- `sender_domain`: the domain portion of the `From` header (e.g. `morningbrew.com`)
- `jmap_message_id`: the opaque string ID returned by Stalwart JMAP (e.g. `M1a2b3c4`)
- Example: `newsletter:///morningbrew.com/M1a2b3c4`

### 3.3 Parser

```python
class NewsletterParser(ParserStrategy):
    source_type: SourceType = SourceType.NEWSLETTER

    def can_handle(self, source: str) -> bool:
        """Returns True iff source starts with 'newsletter:///'."""

    def parse(self, source: str) -> SourceInfo:
        """
        Accepts a pre-formed newsletter:/// URI (constructed by the sync loop).
        Validates the URI structure; raises ValueError on malformed input.
        Returns SourceInfo with uri=source, original_source=source, hash=None.
        """
```

### 3.4 Extractor

```python
class NewsletterExtractor(ExtractorStrategy):
    source_type: SourceType = SourceType.NEWSLETTER

    def extract(self, source: SourceInfo) -> ContentData:
        """
        Opens a JMAP session using env var credentials.
        Fetches the full message body for the JMAP ID encoded in source.uri.
        Extracts HTML part; raises SiphonExtractorError if no HTML part found.
        Converts HTML → markdown via readabilipy + markdownify.
        Raises SiphonExtractorError if readabilipy returns empty content.
        Extracts all <a href> links from the HTML; stores as metadata['links'].
        Returns ContentData with text=markdown, metadata as specified below.
        """
```

**ContentData.metadata shape:**
```python
{
    "jmap_id":       str,   # raw JMAP message ID
    "sender_domain": str,   # domain from From header
    "from":          str,   # full raw From header value
    "subject":       str,   # Subject header
    "date":          str,   # Date header (raw RFC 2822 string)
    "links":         list[str],  # all href URLs extracted from HTML body
}
```

### 3.5 Enricher

```python
class NewsletterEnricher(EnricherStrategy):
    source_type: SourceType = SourceType.NEWSLETTER

    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        """
        Generates title, description, summary via conduit ModelAsync.
        Uses prompts/newsletter_description.jinja2 and prompts/newsletter_summary.jinja2.
        Title is derived from Subject header (content.metadata['subject']) — no LLM call needed.
        Description and summary are generated concurrently via asyncio.gather.
        """
```

### 3.6 JMAP Client (internal module)

```python
# sources/newsletter/jmap_client.py

class NewsletterJMAPClient:
    def __init__(self, url: str, user: str, password: str) -> None: ...

    def get_session(self) -> dict: ...
        """Fetches /.well-known/jmap, returns session object."""

    def query_since(self, account_id: str, since_epoch: int) -> list[str]:
        """
        Email/query with filter receivedAt >= since_epoch.
        Returns list of JMAP message IDs.
        """

    def get_envelopes(self, account_id: str, ids: list[str]) -> list[dict]:
        """
        Email/get fetching only id, from, subject, receivedAt fields (no body).
        Batch call — all IDs in one request.
        Returns list of message envelope dicts.
        """

    def get_body(self, account_id: str, jmap_id: str) -> str:
        """
        Email/get fetching bodyValues for a single message.
        Returns the raw HTML string of the text/html body part.
        Raises SiphonExtractorError if no HTML part exists.
        """
```

### 3.7 Sync CLI

```
siphon fetch newsletters [--since <spec>] [--concurrency <n>] [--dry-run] [--raw]
```

- `--since`: ISO date (`2026-01-01`), relative (`30d`, `all`). Default: `all` on first run, checkpoint timestamp on subsequent runs.
- `--concurrency`: max simultaneous enrichment pipeline requests. Default: 10.
- `--dry-run`: classify and print what would be processed without writing to DB.
- `--raw`: plain output mode (no Rich).

**Sync phases:**

```
Phase 1 — Classify (no pipeline calls):
  1. Derive checkpoint: MAX(updated_at) WHERE source_type=NEWSLETTER, or 0 if --since all or first run
  2. JMAP Email/query: fetch all message IDs since checkpoint
  3. JMAP Email/get (batch): fetch envelopes (headers only) for all IDs
  4. For each envelope:
     a. Parse From header → extract sender_domain
        Hard error (log + skip message) if From is absent or domain unparseable
     b. Build URI: newsletter:///<sender_domain>/<jmap_id>
     c. Check URI against existing content table → skip if already present
  5. Return queue of (uri, jmap_id, envelope_metadata) tuples

Phase 2 — Process (parallel enrichment):
  1. For each queued item, dispatch through headwater pipeline via asyncio.Semaphore
  2. Batch embed all successfully processed URIs after queue is drained
```

**Retry policy (JMAP HTTP errors):**
- Retry up to 3 times with exponential backoff (1s, 2s, 4s) on connection errors or 5xx responses.
- Do not retry on 4xx (auth failure, bad request) — hard error immediately.

---

## 4. Acceptance Criteria

- `siphon fetch newsletters` with an empty content table and a populated inbox processes all messages and reports N new.
- Re-running immediately after a successful sync reports 0 new (checkpoint correctly excludes already-processed messages).
- A message with an unparseable `From` header is logged with the raw header value and skipped; remaining messages in the batch are processed.
- A message whose HTML body produces empty output from readabilipy raises `SiphonExtractorError` and is logged and skipped.
- `--dry-run` prints the classify report and exits without writing any records to the DB.
- `--since 30d` processes only messages received in the last 30 days, regardless of content table state.
- `newsletter:///morningbrew.com/M1a2b3c4` is accepted by `NewsletterParser.can_handle()`.
- A string not starting with `newsletter:///` returns `False` from `can_handle()`.
- `ContentData.metadata['links']` contains all `<a href>` URLs found in the HTML body.
- `EnrichedData.title` equals `ContentData.metadata['subject']` (no LLM title generation).
- `SourceType.NEWSLETTER` appears in `siphon_api/enums.py` and is accepted by the registry.
- The registry validates the `newsletter/` directory without raising.

---

## 5. Error Handling / Failure Modes

| Failure | Behavior |
|---|---|
| JMAP auth failure (401) | Hard error, abort entire sync run, log credentials env var names (not values) |
| JMAP connection error / 5xx | Retry 3× with exponential backoff; abort run if all retries fail |
| `From` header absent or domain unparseable | Log raw header + jmap_id, skip message, continue batch |
| No HTML body part in message | `SiphonExtractorError`, logged by sync loop, message skipped |
| readabilipy returns empty string | `SiphonExtractorError`, logged by sync loop, message skipped |
| Individual pipeline/enrichment failure | Log error + uri, skip, continue; report error count in summary |
| `embed_batch` failure after processing | Log warning, do not fail the run (records are stored, just not embedded) |

---

## 6. Conventions Reference

Follow this pattern from `ObsidianExtractor` for error handling and metadata construction:

```python
# sources/newsletter/extractor.py
from __future__ import annotations

from typing import override

from siphon_api.enums import SourceType
from siphon_api.errors import SiphonExtractorError
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData, SourceInfo


class NewsletterExtractor(ExtractorStrategy):
    source_type: SourceType = SourceType.NEWSLETTER

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        jmap_id = source.uri.split("/")[-1]
        client = _get_client()  # reads env vars, raises on missing
        html = client.get_body(account_id=client.account_id, jmap_id=jmap_id)
        markdown = _html_to_markdown(html)  # raises SiphonExtractorError if empty
        links = _extract_links(html)
        return ContentData(
            source_type=self.source_type,
            text=markdown,
            metadata={
                "jmap_id": jmap_id,
                "sender_domain": source.uri.split("/")[-2],
                "links": links,
                # remaining fields populated by sync loop via SourceInfo
            },
        )
```

---

## 7. Domain Language

These are the exact nouns the implementation is allowed to use:

| Term | Definition |
|---|---|
| **newsletter** | A single email message received in the dedicated ingestion inbox |
| **sender domain** | The domain portion of the RFC 5322 `From` header (e.g. `morningbrew.com`) |
| **jmap_id** | The opaque string identifier assigned to a message by Stalwart JMAP (e.g. `M1a2b3c4`) |
| **uri** | The canonical siphon identifier for a newsletter: `newsletter:///<sender_domain>/<jmap_id>` |
| **envelope** | The headers-only representation of a message (From, Subject, Date, receivedAt) — no body |
| **checkpoint** | The epoch timestamp derived from `MAX(updated_at)` for `SourceType.NEWSLETTER` in the content table |
| **classify** | Phase 1 of sync: determine which messages are new without running the pipeline |
| **process** | Phase 2 of sync: run new messages through extract → enrich → store |
| **publication** | The sender, identified by sender domain, that a newsletter originates from |
| **links** | All `<a href>` URLs extracted from the HTML body of a newsletter |

Terms that must NOT be used: `email` (use `newsletter`), `imap` (not used), `message_id` (use `jmap_id`), `feed`, `subscription`.

---

## 8. Invalid State Transitions

The following state mutations must raise errors immediately:

- Calling `NewsletterExtractor.extract()` when `NEWSLETTER_JMAP_URL`, `NEWSLETTER_JMAP_USER`, or `NEWSLETTER_JMAP_PASSWORD` is not set → `EnvironmentError`
- Calling `NewsletterParser.parse()` with a URI that does not match `newsletter:///<domain>/<id>` → `ValueError`
- Calling `NewsletterJMAPClient.get_body()` with a `jmap_id` that does not exist in the account → `SiphonExtractorError`
- Calling `NewsletterJMAPClient.query_since()` before `get_session()` has been called → `RuntimeError`
- Writing a newsletter record to the content table with `uri` not matching `^newsletter:///[^/]+/[^/]+$` → must be caught at the URI construction step, not at DB write time

---

## Implementation Prerequisites (DevOps)

Before implementation begins, the following must be in place on **nimzo** (`204.168.191.144`):

- [ ] Stalwart Mail Server installed and running
- [ ] JMAP endpoint reachable at `NEWSLETTER_JMAP_URL`
- [ ] Dedicated newsletter inbox account created
- [ ] App password generated and stored as `NEWSLETTER_JMAP_PASSWORD`
- [ ] MX records configured for the newsletter domain
- [ ] Test: `curl -u user:password <NEWSLETTER_JMAP_URL>` returns a valid JMAP session object
