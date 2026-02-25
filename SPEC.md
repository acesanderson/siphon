# Siphon Source Types: Implementation Spec

## Overview

Six new SourceTypes are added to the siphon pipeline: ARXIV, IMAGE, VIDEO, EMAIL, GITHUB, OBSIDIAN.
Each follows the same 3-stage pipeline: Parser → Extractor → Enricher.

---

## ARXIV

### can_handle
- Bare arXiv IDs matching `\d{4}\.\d{4,5}` (e.g. `2301.12345`)
- URLs containing `arxiv.org/abs/` or `arxiv.org/pdf/`

### URI scheme
`arxiv:///{id}` — e.g. `arxiv:///2301.12345`

### Extractor
- Fetches `http://export.arxiv.org/api/query?id_list={id}` (Atom XML, no auth)
- Parses with `xml.etree.ElementTree`
- `text` = abstract text
- metadata: `title`, `authors`, `categories`, `published`, `arxiv_id`, `pdf_url`

### Enricher
- Standard conduit enricher
- Prompts: `arxiv_description.jinja2`, `arxiv_summary.jinja2`, `title.jinja2`
- No auth required

### Caching
- Standard cache behavior; re-ingesting same ID returns cached result

---

## IMAGE

### can_handle
- File path that exists AND suffix in `EXTENSIONS["Image"]`
- URL ending in an image extension (`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.svg`, `.webp`, `.ico`)

### URI scheme
`image:///{ext}/{hash}` — hash is sha256 of file bytes (first 16 chars) or sha256 of URL string

### Extractor
- Reads image bytes (from file or HTTP download)
- Encodes as base64
- Calls vision model via conduit (`asyncio.run(...)`) with base64 image in prompt
- `text` = vision model's description of the image
- metadata: `file_name`, `extension`, `mime_type`
- NOTE: a local vision worker is planned; current impl delegates to conduit

### Enricher
- Standard conduit enricher operating on the vision description
- Prompts: `image_description.jinja2`, `image_summary.jinja2`, `title.jinja2`

### Caching
- Standard cache behavior

---

## VIDEO

### can_handle
- File path that exists AND suffix in `EXTENSIONS["Video"]`
- Does NOT match YouTube URLs (those go to YOUTUBE source)

### URI scheme
`video:///{ext}/{hash}` — sha256 of file bytes (first 16 chars)

### Extractor
- Strips audio track via ffmpeg: `ffmpeg -i {input} -vn -acodec pcm_s16le -ar 44100 -ac 2 {tmp.wav}`
- Calls `retrieve_audio(tmp_wav_path)` from `sources/audio/pipeline/audio_pipeline.py`
- Returns same ContentData shape as Audio

### Enricher
- Copy of AudioEnricher with `source_type = SourceType.VIDEO`
- Prompts: `video_description.jinja2`, `video_summary.jinja2`, `title.jinja2`

### Caching
- Standard cache behavior

---

## EMAIL

### can_handle
- Gmail message URL containing `mail.google.com` (e.g. `https://mail.google.com/mail/u/0/#inbox/18abc123def456ab`)
- Bare Gmail message ID matching `[0-9a-f]{16}`

### URI scheme
`email:///gmail/{message_id}`

### Extractor
- Gmail API via `google-auth` + `google-api-python-client`
- Auth: token file at `GMAIL_TOKEN_FILE` env var (default: `~/.config/siphon/gmail_token.json`)
- Client secret at `GMAIL_CLIENT_SECRET_FILE` env var (default: `~/.config/siphon/gmail_client_secret.json`)
- Fetches message by ID, decodes MIME, extracts plain-text body
- metadata: `message_id`, `from`, `to`, `subject`, `date`, `thread_id`

### Enricher
- Standard conduit enricher
- Prompts: `email_description.jinja2`, `email_summary.jinja2`, `title.jinja2`

### Auth requirements
- Gmail OAuth2 credentials required. Obtain from Google Cloud Console.
- Token is cached at `GMAIL_TOKEN_FILE` after first auth flow.

### Caching
- Standard cache behavior

---

## GITHUB

### can_handle
- URLs matching `github.com/{owner}/{repo}` pattern
- Normalizes away `/tree/...`, `/blob/...`, trailing `.git`

### URI scheme
`github:///{owner}/{repo}`

### Extractor
- GitHub API via `httpx` with `Authorization: Bearer {GITHUB_TOKEN}` header
- `GITHUB_TOKEN` env var optional for public repos
- Fetches recursive file tree: `GET /repos/{owner}/{repo}/git/trees/HEAD?recursive=1`
- Filters out: `.json`, `.lock`, `.toml`, `.yaml`, `.yml`, binary files
- Fetches each remaining file content via `GET /repos/{owner}/{repo}/contents/{path}`
- Builds XML blob: `<repository owner="{owner}" repo="{repo}"><file path="{path}">{content}</file>...</repository>`
- metadata: `owner`, `repo`, `default_branch`, `file_count`, `fetched_at`
- NOTE: pass `use_cache=False` to force refresh of an already-ingested repo

### Enricher
- Standard conduit enricher
- Prompts: `github_description.jinja2`, `github_summary.jinja2`, `title.jinja2`

### Auth requirements
- `GITHUB_TOKEN` env var recommended for private repos and to avoid rate limits

### Caching caveat
- GitHub repos change over time. Upsert (re-ingest) rather than deduplication by hash.
- The hash in SourceInfo is deterministic from owner/repo — callers must explicitly pass `use_cache=False` to force re-fetch.

---

## OBSIDIAN

### can_handle
- Path that exists AND is a `.md` file AND is inside an Obsidian vault
- Vault detection: walk up parent directories until a dir containing `.obsidian/` subdirectory is found

### URI scheme
`obsidian:///{hash}` — sha256 of canonical absolute path (first 16 chars)

### Extractor
- Finds vault root by walking up from the note's directory
- Reads the root note
- Parses `[[wikilink]]` and `[[wikilink|alias]]` patterns with regex
- Resolves linked note paths relative to vault root (recursive search for `{wikilink}.md`)
- Recursively fetches linked notes with cycle detection (set of visited absolute paths)
- Concatenates as structured markdown: `# {note_title}\n\n{content}\n\n---\n\n# {linked_title}\n\n{linked_content}...`
- metadata: `root_note`, `vault_root`, `note_count`

### Enricher
- Standard conduit enricher
- Prompts: `obsidian_description.jinja2`, `obsidian_summary.jinja2`, `title.jinja2`

### Caching
- Standard cache behavior; hash is stable for same absolute path

---

## ArticleParser Exclusion List Update

The following domains are added to the exclusion list so ArticleParser does not claim these sources:
- `mail.google.com` (handled by EMAIL)
- `github.com` (handled by GITHUB)
- `arxiv.org` (handled by ARXIV)
