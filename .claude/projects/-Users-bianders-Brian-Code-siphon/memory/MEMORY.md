# Siphon Project Memory

## Behavioral Rules

- [Local models only — no cloud fallbacks](feedback_local_models_only.md) — Never substitute haiku/gpt-mini/etc. when user requests local model inference
- [CLI first, direct calls only as fallback](feedback_cli_before_direct_calls.md) — Always try conduit CLI before HeadwaterAsyncClient or direct DB calls

## Infrastructure

### nimzo VPS
- IP: 204.168.191.144
- User: root
- SSH key: ~/.ssh/Petrosian
- SSH host alias: `nimzo`
- Purpose: personal VPS, running Stalwart Mail Server for newsletter ingestion

### Stalwart Mail Server (on nimzo)
- Self-hosted email server supporting IMAP, JMAP, SMTP
- Used as the email endpoint for the siphon `newsletter` passive source
- Auth: app password / API key (no OAuth)
- Chosen over Fastmail (paid), Migadu (paid), Gmail (OAuth pain)

## Project Structure

- Source types live in `siphon-server/src/siphon_server/sources/`
- Each source needs: `parser.py`, `extractor.py`, `enricher.py` (validated by registry)
- Passive sources (mollusk pattern): obsidian, email, podcasts, arxiv, newsletter
- Active sources (snail pattern): youtube, article, doc
- Sync CLI lives in `siphon-client/src/siphon_client/cli/`
- Passive source commands: `siphon fetch <source>` namespace

## Newsletter Source Design (in progress)

- Protocol: IMAP (or JMAP) against Stalwart on nimzo
- Credentials via env vars: `NEWSLETTER_IMAP_HOST`, `NEWSLETTER_IMAP_USER`, `NEWSLETTER_IMAP_PASSWORD`
- URI scheme: `newsletter:///<sender_domain>/<message_id>`
- Extraction: HTML → markdown via readabilipy + markdownify (same as ArticleExtractor)
- Linked URLs stored as metadata (parallel to Obsidian wikilinks)
- Checkpoint: timestamp (for IMAP query) + message-ID set in Postgres (for dedup)
- No automated pruning — append-only, manual pruning only
- Extraction failure: hard error, logged and skipped by sync loop
- CLI: `siphon fetch newsletters`
- Single document enrichment per newsletter (no splitting of roundups)

## Worker Sidecars (alphablue)

- [granite-speech eval — shelved](project_granite_speech_eval.md) — IBM granite-speech-4.1-2b-plus not production-ready; whisper + pyannote already covers the use case
