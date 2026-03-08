# Siphon

Siphon is a multi-source content ingestion and retrieval pipeline designed to transform heterogeneous data—YouTube videos, web articles, local documents, Obsidian vaults, and emails—into structured, searchable, and LLM-enriched knowledge.

## Table of Contents
- [Quick Start](#quick-start)
- [Core Pipeline Architecture](#core-pipeline-architecture)
- [Installation and Setup](#installation-and-setup)
- [CLI Reference](#cli-reference)
- [Supported Source Types](#supported-source-types)
- [Configuration](#configuration)

## Quick Start

### Installation
Install the Siphon packages using `uv` or `pip`:

```bash
# Install the client and server components
pip install siphon-api siphon-client siphon-server
```

### Initial Ingestion
Ingest a source (e.g., a YouTube video) to parse, extract, and enrich it using LLMs:

```bash
siphon gulp "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Retrieval
Search for ingested content using the SQL-based text search:

```bash
siphon query "Rick Astley" --limit 5
```

## Core Pipeline Architecture

Siphon operates as an orchestrated pipeline consisting of four distinct stages. This modularity allows for specific offramps depending on the desired outcome (e.g., extracting text without persisting to the database).

| Stage | Component | Input | Output |
| :--- | :--- | :--- | :--- |
| **1. Parse** | `SourceParser` | Raw String/URL | `SourceInfo` (Canonical URI) |
| **2. Extract** | `ContentExtractor` | `SourceInfo` | `ContentData` (Raw Text + Metadata) |
| **3. Enrich** | `ContentEnricher` | `ContentData` | `EnrichedData` (LLM Summary/Description) |
| **4. Persist** | `Repository` | `ProcessedContent` | Database Record |

### Action Types
The CLI and API support early termination of the pipeline via the `--return-type` or `action` parameter:

- `parse`: Resolves the source to a canonical URI.
- `extract`: Returns raw text and metadata (ephemeral).
- `enrich`: Returns LLM-generated summaries (ephemeral).
- `gulp`: Executes the full pipeline and persists the result to PostgreSQL.

## Installation and Setup

### Prerequisites
- **Python**: 3.12 or higher.
- **Database**: PostgreSQL with the `pgvector` extension.
- **LLM Access**: Configured `conduit` provider for enrichment.
- **System Dependencies**: `ffmpeg` (for audio/video processing).

### Environment Variables
The following variables are required for database connectivity and external API access:

| Variable | Description |
| :--- | :--- |
| `POSTGRES_USERNAME` | PostgreSQL user. |
| `POSTGRES_PASSWORD` | PostgreSQL password. |
| `HUGGINGFACEHUB_API_TOKEN` | Token for audio diarization and vision models. |
| `YOUTUBE_API_KEY2` | Optional key for advanced YouTube metadata. |
| `WEBSHARE_USERNAME` | Proxy username for YouTube transcript bypassing. |
| `WEBSHARE_PASS` | Proxy password for YouTube transcript bypassing. |

### Database Initialization
Run the setup script to provision the schema:

```bash
python -m siphon_server.database.postgres.setup
```

## CLI Reference

### Ingestion Commands

#### gulp
Processes a source and persists it to the database.
```bash
siphon gulp "path/to/document.pdf" --return-type s
```

#### sync
Bulk ingests an Obsidian vault. It performs client-side change detection to only process new or significantly modified notes.
```bash
siphon sync --vault ~/my-obsidian-vault --concurrency 10
```

### Retrieval Commands

#### query
Search the content database. Supports filtering by type, date, and file extension.
```bash
siphon query "machine learning" --type doc --extension pdf
```

#### traverse
Walk the wikilink graph from a specific node (primarily for Obsidian).
```bash
siphon traverse "Project Phoenix" --depth 2 --backlinks
```

#### results
Access query history and retrieve specific items by their index from previous searches.
```bash
siphon results --history
siphon query --get 2 --return-type c
```

## Supported Source Types

| Type | Parser Logic | Extraction Method |
| :--- | :--- | :--- |
| **YouTube** | URL detection | `yt-dlp` metadata + `youtube-transcript-api` |
| **Article** | Web URL (non-social) | `readabilipy` + `markdownify` |
| **Doc** | `.pdf`, `.docx`, `.txt`, `.csv` | `MarkItDown` conversion |
| **Audio** | `.mp3`, `.wav`, `.m4a` | Whisper Transcription + Pyannote Diarization |
| **GitHub** | Repository URL | GitHub API tree traversal |
| **Obsidian** | Vault-internal `.md` | Wikilink extraction + Frontmatter parsing |
| **Email** | Gmail URL/ID | Google OAuth + Gmail API |
| **Image** | `.jpg`, `.png`, `.svg` | Vision-LLM description |

## Configuration

Siphon looks for a configuration file at `~/.config/siphon/config.toml`.

```toml
default_model = "gpt-4o"
log_level = 2
cache = true
vault = "~/vaults/main"
```

### Component Structure
- `siphon-api`: Shared Pydantic models and interface definitions.
- `siphon-server`: Pipeline orchestration, database logic, and source strategies.
- `siphon-client`: CLI implementation and high-level client wrappers.
- `workers`: Isolated sidecar services for heavy ML tasks (Diarization, Flux Image Gen).
