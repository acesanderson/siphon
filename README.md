# Siphon

Transform any content source into structured, searchable, LLM-ready knowledge while retaining complete control over your data. Built for the age of AI agents, designed for minds that work in parallel.

## Philosophy

In the age of AI, human cognitive work is shifting to a higher altitude—managing context, connecting ideas, and making strategic decisions on the fly. Yet we're still trapped in fragmented tools with inconsistent search, scattered across Outlook, Google Drive, Slack, and dozens of other silos.

Siphon operates on four core principles:

1. **Everything is LLM context** — The process of converting any data source into usable context should be frictionless
2. **Retention vs. recall** — Save everything, optimize for retrieval. Embrace the chaos of an arbitrary corpus rather than forcing hierarchical organization
3. **Frictionless context engineering** — Assembling the right context for LLM tasks should be effortless
4. **Optimize for human efficiency** — Use AI to eliminate information silos and accelerate knowledge work

## What Siphon Does

**Process once, query forever.** Siphon converts any content source into structured, cached knowledge:

```bash
# Ingest anything
siphon quarterly-strategy.pdf
siphon https://www.youtube.com/watch?v=xyz  
siphon https://github.com/company/repo
siphon podcast.m4a
siphon competitive-analysis.pptx

# Get what you need
siphon document.pdf -r s    # Summary for quick scanning
siphon audio.mp3 -r c       # Full context for LLM input
siphon --last               # Retrieve last processed item
```

Every source becomes a **ProcessedContent** object with:
- **Raw LLM context** — Clean, structured text ready for any AI model
- **AI-generated enrichments** — Searchable titles, descriptions, and summaries
- **Source-specific metadata** — YouTube view counts, GitHub stars, document modification times
- **Persistent caching** — Process once, access instantly

## The Siphon Advantage

### Universal Ingestion Engine
11 source types supported:

| **Content Type** | **Examples** | **Processing** |
|------------------|--------------|----------------|
| **Documents** | `.pdf`, `.docx`, `.pptx`, `.xlsx` | MarkItDown conversion with structure preservation |
| **Audio/Video** | `.mp3`, `.wav`, `.m4a`, `.mp4` | Whisper transcription + pyannote diarization |
| **Code** | GitHub repos, local directories | XML flattening for LLM analysis |
| **Web Content** | Articles, YouTube videos | Clean text extraction + metadata |
| **Images** | `.jpg`, `.png`, `.gif` | Vision model descriptions (local or cloud) |
| **Text** | `.md`, `.txt`, `.py`, `.json` | Direct ingestion with checksums |

### Intelligent Caching System
PostgreSQL primary cache with SQLite fallback ensures resilience:

```bash
siphon important-doc.pdf        # First run: full processing
siphon important-doc.pdf        # Instant retrieval from cache
```

The fallback system automatically:
- Detects PostgreSQL availability
- Falls back to SQLite when needed
- Queues items for sync when connection restored
- Provides cache statistics and monitoring

### Research Synthesis
Multi-document analysis with async LLM processing:

```bash
survey_cli.py "Company's AI strategy" --dir ./competitive-intel/
# Analyzes directory, extracts relevant insights, synthesizes findings
```

## Quick Start

### Installation
```bash
pip install -e .

# Audio processing dependencies
brew install portaudio ffmpeg  # macOS
# OR
sudo apt-get install portaudio19-dev ffmpeg  # Ubuntu
```

### Environment Setup
```bash
export POSTGRES_PASSWORD="your_password"
export GITHUB_TOKEN="your_token"           # For GitHub repos
export OPENAI_API_KEY="your_key"           # Optional: cloud processing
export YOUTUBE_API_KEY="your_key"          # Optional: YouTube playlists
```

### Basic Usage

```bash
# Process content
siphon strategy-doc.pdf
siphon "https://youtube.com/watch?v=abc123"
siphon "https://github.com/company/repo"

# Control output format
siphon doc.pdf -r s         # Summary only
siphon doc.pdf -r c         # Full context
siphon doc.pdf -r u         # URI only
siphon doc.pdf --pretty     # Rich terminal display

# Cache options
siphon doc.pdf -c u         # Uncached (don't save)
siphon doc.pdf -c r         # Recache (force reprocess)
siphon doc.pdf -c c         # Cached (default)

# Tagging
siphon doc.pdf -t "strategy,Q1,competitive"

# Get last processed
siphon --last
```

## Architecture

### Core Pipeline
```
Source → URI → Context → SyntheticData → ProcessedContent → Cache
```

**1. URI Layer** (`src/siphon/uri/`)
- Factory pattern for source identification
- 11 URI subclasses (TextURI, YouTubeURI, GitHubURI, etc.)
- Checksum-based deduplication for file sources
- Consistent URI format across all types

**2. Context Layer** (`src/siphon/context/`)
- Source-specific content extraction
- 11 Context subclasses matching URI types
- Metadata preservation per source type
- Validation and error handling

**3. Synthetic Data Layer** (`src/siphon/synthetic_data/`)
- AI-generated enrichments (title, description, summary)
- Async batch processing via Conduit
- Jinja2 templates for source-specific prompts
- Local or cloud LLM support

**4. Storage Layer** (`src/siphon/database/`)
- PostgreSQL primary cache with JSONB storage
- SQLite fallback with automatic sync queue
- Vector embeddings for semantic search (pgvector)
- Cache statistics and monitoring

### Key Modules

**CLI** (`src/siphon/cli/`)
- `siphon_cli.py` — Main command-line interface
- `cli_params.py` — Pydantic-validated parameters
- `implicit_input.py` — Clipboard and stdin detection

**Data Models** (`src/siphon/data/`)
- `processed_content.py` — Final output format
- `uri.py` — Base URI class
- `context.py` — Base context class
- `synthetic_data.py` — AI enrichment base class

**Ingestion** (`src/siphon/ingestion/`)
- Source-specific retrieval logic
- `audio/` — Whisper + diarization pipeline
- `github/` — Repository flattening
- `youtube/` — Transcript + metadata extraction
- `image/` — Vision model descriptions

**Enrichment** (`src/siphon/enrich/`)
- Title, description, and summary generation
- Adaptive summary lengths based on content size
- Model selection (local or cloud)

**Collections** (`src/siphon/collections/`)
- Corpus management system
- Query interface (filtering, sorting, pagination)
- Snapshot generation for visualization

### Database Architecture

PostgreSQL schema:
```sql
CREATE TABLE processed_content (
    id SERIAL PRIMARY KEY,
    uri_key TEXT UNIQUE NOT NULL,
    data JSONB NOT NULL,
    description_embedding vector(384),
    summary_embedding vector(384),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Indexes:
- B-tree on `uri_key` for cache lookups
- GIN on `data` for JSONB queries
- HNSW on embeddings for vector search

## Advanced Workflows

### Competitive Intelligence
```bash
# Ingest sources
siphon competitor-earnings.mp3
siphon industry-report.pdf
siphon https://youtube.com/watch?v=product-demo

# Synthesize findings
survey_cli.py "AI strategy and positioning" --dir ./intel/
```

### GitHub Repository Analysis
```bash
# Flatten repository to XML
flatten_cli.py https://github.com/owner/repo > repo.xml

# Process for LLM context
siphon https://github.com/owner/repo
```

### Audio/Video Processing
```bash
# Local transcription (Whisper + diarization)
siphon meeting.mp3

# Cloud transcription (OpenAI)
siphon meeting.mp3 -C

# Play audio files
play_cli.py recording.mp3

# Record new audio
record_cli.py
```

### Image Analysis
```bash
# OCR text extraction
ocr_cli.py screenshot.png

# AI description
siphon diagram.png

# View in terminal
peek_cli.py image.jpg
```

### YouTube Operations
```bash
# Single video
siphon "https://youtube.com/watch?v=xyz"

# Entire playlist (combined transcript)
youtube_cli.py "https://youtube.com/playlist?list=PLxxx"

# Channel video list
youtube_cli.py "https://youtube.com/@channelname"
```

## Python API

```python
from siphon import siphon
from siphon.cli.cli_params import CLIParams

# Basic usage
content = siphon("document.pdf")

# With parameters
params = CLIParams(
    source="document.pdf",
    cache_options="c",
    cloud=False,
    tags=["strategy", "Q1"]
)
content = siphon(params)

# Access processed content
print(content.title)
print(content.summary)
print(content.context)

# Pretty display
content.pretty_print()

# Access metadata
print(content.uri.sourcetype)
print(content.created_at)
```

### Database Operations
```python
from siphon.database.postgres.PGRES_processed_content import (
    get_cached_content,
    cache_processed_content,
    get_all_siphon,
    search_cached_content
)

# Retrieve cached content
content = get_cached_content("text:///path/to/file.md")

# Cache new content
uri_key = cache_processed_content(processed_content)

# Search
results = search_cached_content(
    source_type="YouTube",
    title_query="machine learning",
    limit=10
)

# Get statistics
from siphon.database.postgres.PGRES_processed_content import get_cache_stats
stats = get_cache_stats()
```

### Collections API
```python
from siphon.collections.corpus.siphon_corpus import CorpusFactory

# Create corpus
corpus = CorpusFactory.from_library()

# Query interface
results = (
    corpus.query()
    .filter_by_source_type(SourceType.ARTICLE)
    .filter_by_content("AI strategy")
    .order_by_date(ascending=False)
    .limit(10)
    .to_list()
)

# Semantic search
similar = (
    corpus.query()
    .semantic_search("machine learning tutorials", k=5)
    .to_list()
)

# Generate snapshot
corpus.snapshot()
```

## Command-Line Tools

### Core Tools
- `siphon` — Main ingestion and retrieval
- `flatten_cli.py` — Convert repos/directories to XML
- `survey_cli.py` — Multi-document research synthesis

### Audio Tools
- `record_cli.py` — Record audio with CLI interface
- `play_cli.py` — Play audio files
- `ocr_cli.py` — Extract text from images

### Visual Tools
- `peek_cli.py` — Display images in terminal (chafa)

### YouTube Tools
- `youtube_cli.py` — Process playlists and channels

### Utility Tools
- `obsidian_cli.py` — Fetch date range from Obsidian vault
- `test_sourcetype.py` — Debug individual source types

## Database Management

### Cache Operations
```bash
# View cache snapshot
python -m siphon.database.sqlite.snapshot_sqlite3

# PostgreSQL snapshot
python -m siphon.collections.query.snapshot

# Manual sync (SQLite → PostgreSQL)
python -m siphon.database.sqlite.manual_sync

# Get fallback statistics
python -c "from siphon.database.postgres.PGRES_processed_content import get_fallback_stats; print(get_fallback_stats())"
```

### Cache Flags
- `-c c` (default) — Use cache if available
- `-c u` — Uncached, don't save to cache
- `-c r` — Recache, force reprocessing

## Configuration

### Required Environment Variables
```bash
POSTGRES_PASSWORD      # PostgreSQL authentication
```

### Optional Environment Variables
```bash
GITHUB_TOKEN          # GitHub API access
OPENAI_API_KEY        # Cloud LLM processing
YOUTUBE_API_KEY       # YouTube playlist/channel operations
OBSIDIAN_VAULT        # Obsidian vault path
```

### Database Configuration
PostgreSQL connection managed via `dbclients` package:
- Database: `siphon`
- User: System username
- Host: Auto-detected (localhost, 10.0.0.82, or 68.47.92.102)
- Port: 5432

SQLite fallback:
- Location: `~/.siphon/fallback_cache.db`
- Auto-created on first use

## Testing

```bash
# Run all tests
pytest

# Specific test suites
pytest src/siphon/tests/test_uri.py
pytest src/siphon/tests/test_context.py
pytest src/siphon/tests/test_integration.py

# Test specific source type
python src/siphon/scripts/test_sourcetype.py Text
```

## Extending Siphon

### Adding New Source Types

1. **Define in SourceType enum** (`src/siphon/data/type_definitions/source_type.py`)
```python
class SourceType(str, Enum):
    MYNEWTYPE = "MyNewType"
```

2. **Create URI class** (`src/siphon/uri/classes/mynewtype_uri.py`)
```python
class MyNewTypeURI(URI):
    sourcetype: SourceType = SourceType.MYNEWTYPE
    
    @classmethod
    def identify(cls, source: str) -> bool:
        # Detection logic
        pass
    
    @classmethod
    def from_source(cls, source: str) -> "MyNewTypeURI":
        # URI creation logic
        pass
```

3. **Create Context class** (`src/siphon/context/classes/mynewtype_context.py`)
```python
class MyNewTypeContext(Context):
    sourcetype: SourceType = SourceType.MYNEWTYPE
    
    @classmethod
    def from_uri(cls, uri: URI) -> "MyNewTypeContext":
        # Content extraction logic
        pass
```

4. **Create SyntheticData class** (`src/siphon/synthetic_data/classes/mynewtype_synthetic_data.py`)
```python
class MyNewTypeSyntheticData(TextSyntheticData):
    sourcetype: SourceType = SourceType.MYNEWTYPE
    # Inherits from TextSyntheticData unless custom logic needed
```

5. **Add prompt templates** (`src/siphon/prompts/synthetic_data/`)
- `mynewtype_title.jinja2`
- `mynewtype_description.jinja2`
- `mynewtype_summary.jinja2`

## Dependencies

### Core Dependencies
- `pydantic` — Data validation
- `psycopg2` — PostgreSQL client
- `rich` — Terminal formatting
- `jinja2` — Template rendering
- `conduit` — LLM abstraction (local project)

### Ingestion Dependencies
- `newspaper3k` — Article extraction
- `youtube-transcript-api` — YouTube transcripts
- `yt-dlp` — YouTube metadata
- `markitdown` — Document conversion
- `PyGithub` — GitHub API
- `requests` — HTTP client

### Audio/Video Dependencies
- `torch` — PyTorch for ML models
- `transformers` — Whisper transcription
- `pyannote