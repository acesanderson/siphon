# Siphon Refactor: Complete Architecture Design Document

**Version:** 2.0  
**Date:** October 24, 2025  
**Status:** Design Phase

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Three-Package Architecture](#three-package-architecture)
3. [Current Problems](#current-problems)
4. [Design Philosophy](#design-philosophy)
5. [Package Structure](#package-structure)
6. [Core Data Models](#core-data-models)
7. [Pipeline Architecture](#pipeline-architecture)
8. [Domain-Driven Design](#domain-driven-design)
9. [Adding New Source Types](#adding-new-source-types)
10. [Client Collections API](#client-collections-api)
11. [Server API Endpoints](#server-api-endpoints)
12. [Deployment Architecture](#deployment-architecture)
13. [Migration Strategy](#migration-strategy)
14. [Trade-offs & Design Decisions](#trade-offs--design-decisions)
15. [Future Roadmap](#future-roadmap)

---

## Executive Summary

Siphon is being refactored from a monolithic architecture with 33+ classes and mixed client/server logic into a clean three-package system:

1. **siphon-api** - Shared DTOs and interfaces (Python + TypeScript)
2. **siphon-server** - Processing pipeline on ML server (RTX 5090)
3. **siphon-client** - Thin HTTP client + query DSL

### Key Changes

**Before:**
- 33 classes (3 per source type: URI, Context, SyntheticData)
- Business logic embedded in Pydantic models
- Half-local, half-remote processing
- Discriminated union serialization failures
- Client requires GPU, whisper, yt-dlp, etc.

**After:**
- 4 flat DTO classes (no subclasses)
- Explicit pipeline with pluggable strategies
- All processing server-side
- Clean JSON serialization
- Client has zero heavy dependencies

### Benefits

- **Developer Experience:** Add new source in ~1 hour, contained in one directory
- **Deployment:** Server on ML box, client anywhere (Mac, mobile, browser)
- **Testing:** Mock individual pipeline steps, isolated bounded contexts
- **Debugging:** Clear separation, explicit data flow
- **Performance:** GPU operations stay on server, client is instant

---

## Three-Package Architecture

### Package Overview

```
siphon/
├── packages/
│   ├── siphon-api/          # Package 1: Shared contracts
│   ├── siphon-server/       # Package 2: Processing backend
│   └── siphon-client/       # Package 3: Client SDK
```

### Package 1: siphon-api

**Purpose:** Shared data models and interfaces  
**Language:** Python (with TypeScript generation)  
**Dependencies:** `pydantic` only  
**Installation:** `pip install siphon-api`

```
siphon-api/
├── pyproject.toml
├── src/
│   └── siphon_api/
│       ├── __init__.py
│       ├── models.py          # SourceInfo, ContentData, EnrichedData, ProcessedContent
│       ├── interfaces.py      # ParserStrategy, ExtractorStrategy protocols
│       ├── enums.py           # SourceType enum
│       └── typescript/        # Generated TS types (via datamodel-code-generator)
│           └── models.ts
└── tests/
```

**Key Principle:** This package is a **contract**. Changes here affect both server and client, so changes must be:
- Backward compatible
- Versioned (semantic versioning)
- Well-documented

### Package 2: siphon-server

**Purpose:** Content processing pipeline  
**Language:** Python 3.12+  
**Dependencies:** Heavy ML libs (torch, whisper, transformers, yt-dlp, etc.)  
**Hardware:** Requires RTX 5090 (specific CUDA drivers)  
**Installation:** `pip install siphon-server`

```
siphon-server/
├── pyproject.toml            # Dependencies: siphon-api, fastapi, torch, whisper, etc.
├── src/
│   └── siphon_server/
│       ├── __init__.py
│       ├── core/             # Pipeline orchestration (domain-agnostic)
│       │   ├── pipeline.py
│       │   ├── cache.py
│       │   ├── enrichment.py
│       │   └── registry.py
│       │
│       ├── sources/          # Bounded contexts (DDD)
│       │   ├── youtube/
│       │   │   ├── domain/
│       │   │   │   ├── parser.py
│       │   │   │   ├── extractor.py
│       │   │   │   └── models.py
│       │   │   ├── infrastructure/
│       │   │   │   ├── yt_dlp_client.py
│       │   │   │   └── youtube_api.py
│       │   │   └── tests/
│       │   │
│       │   ├── audio/
│       │   │   ├── domain/
│       │   │   ├── infrastructure/
│       │   │   │   ├── whisper_client.py
│       │   │   │   └── pyannote_diarizer.py
│       │   │   └── tests/
│       │   │
│       │   ├── github/
│       │   ├── reddit/
│       │   ├── article/
│       │   └── files/
│       │       ├── text/
│       │       ├── doc/
│       │       ├── image/
│       │       └── video/
│       │
│       ├── api/              # HTTP API layer
│       │   ├── app.py        # FastAPI application
│       │   ├── routes.py     # Endpoint definitions
│       │   ├── dependencies.py
│       │   └── middleware.py
│       │
│       ├── database/         # Persistence
│       │   ├── postgres.py
│       │   ├── pgvector.py
│       │   └── cache.py
│       │
│       └── config.py         # Server configuration
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

**Key Principle:** Server owns **ALL** processing. Client never does extraction, transcription, or enrichment.

### Package 3: siphon-client

**Purpose:** Thin HTTP client + query DSL  
**Language:** Python 3.10+ (no special dependencies)  
**Dependencies:** `httpx`, `siphon-api` only  
**Installation:** `pip install siphon-client`

```
siphon-client/
├── pyproject.toml            # Dependencies: siphon-api, httpx, rich (for display)
├── src/
│   └── siphon_client/
│       ├── __init__.py
│       ├── client.py         # HTTP client (SiphonClient class)
│       ├── collections/      # Monadic query DSL
│       │   ├── __init__.py
│       │   ├── collection.py
│       │   ├── query_builder.py
│       │   └── operations.py
│       ├── display.py        # Rich formatting (ProcessedContent.pretty_print())
│       └── cli.py            # CLI interface
│
└── tests/
    ├── test_client.py
    ├── test_collections.py
    └── fixtures/
```

**Key Principle:** Client is **dumb**. Just HTTP calls + local display logic. Works on Mac, Linux, Windows, mobile, browser (via JS port).

### Dependency Isolation

```
┌─────────────┐
│ siphon-api  │  ← Core contracts (pydantic only)
└─────────────┘
       ▲
       │ imports
       │
┌──────┴──────────┐
│                 │
│                 │
┌─────────────┐   ┌──────────────┐
│siphon-server│   │siphon-client │
└─────────────┘   └──────────────┘
     │                    │
     │                    │
  torch, whisper,      httpx, rich
  transformers,        (lightweight)
  yt-dlp, cuda
  (heavyweight)
```

**Critical:** `siphon-server` and `siphon-client` **never** import each other. They only communicate via HTTP and share `siphon-api` models.

---

## Current Problems

### 1. Class Explosion (33 Classes)

**Problem:** Every SourceType spawns 3 subclasses
- `ImageURI`, `AudioURI`, `VideoURI`, ... (11 classes)
- `ImageContext`, `AudioContext`, `VideoContext`, ... (11 classes)
- `ImageSyntheticData`, `AudioSyntheticData`, ... (11 classes)

**Pain:**
- Adding Reddit source = 3 new files
- Discriminated unions fail on JSON deserialization
- Hard to see which class handles what

### 2. Logic in Data Classes

**Problem:** Pydantic models contain business logic
```python
class Context(BaseModel):
    @classmethod
    def from_uri(cls, uri: URI) -> Context:
        # 100 lines of extraction logic here
```

**Pain:**
- Can't serialize methods over HTTP
- Client needs all dependencies to instantiate
- Testing requires full infrastructure

### 3. Bidirectional Dependencies

**Problem:** Every layer imports every other layer
```python
# uri.py imports context.py
# context.py imports synthetic_data.py  
# synthetic_data.py imports uri.py
# All import SourceType
```

**Pain:**
- Circular import risks
- Can't refactor one without touching all
- Tight coupling

### 4. Implicit Pipeline

**Problem:** Processing hidden in factory methods
```python
uri = URI.from_source(source)  # What happens here?
context = Context.from_uri(uri)  # What about here?
synthetic = SyntheticData.from_context(context)  # Or here?
```

**Pain:**
- Can't see full pipeline
- Can't inject mocks per step
- Hard to add logging/retries

### 5. Mixed Client/Server Architecture

**Problem:** Some processing local, some remote
```python
# Sometimes this runs locally
context = Context.from_uri(uri)

# Sometimes it calls server
synthetic_data = SyntheticData.from_context_remote(context)
```

**Pain:**
- Client needs GPU dependencies "just in case"
- Serialization bugs at boundary
- Unclear where code runs

---

## Design Philosophy

### Core Principles

1. **Data classes are DTOs only** - No methods except properties
2. **Pipeline is explicit** - Can see all steps, can inject dependencies
3. **Server owns all processing** - Client is HTTP wrapper
4. **Composition over inheritance** - Strategies, not subclasses
5. **Bounded contexts are isolated** - YouTube doesn't know about Audio

### Architectural Patterns

- **Domain-Driven Design (DDD):** Each source type is a bounded context
- **Strategy Pattern:** Pluggable parsers/extractors per source type
- **Pipeline Pattern:** Explicit orchestration with dependency injection
- **Repository Pattern:** Abstract database access
- **DTO Pattern:** Separate data transfer from domain models

### Design Constraints

1. **Server must run on ML box** - Specific GPU drivers, can't move
2. **Client must be portable** - Mac, Linux, Windows, mobile
3. **API must be versioned** - Breaking changes require new version
4. **Sources must be independent** - Adding Reddit doesn't affect YouTube
5. **Must support offline mode** - SQLite cache when server unreachable

---

## Package Structure

### siphon-api Package (Detailed)

```python
# siphon-api/src/siphon_api/models.py
from pydantic import BaseModel, Field
from typing import Any
from .enums import SourceType

class SourceInfo(BaseModel):
    """
    Parsed source metadata. Replaces all URI subclasses.
    """
    source_type: SourceType
    uri: str  # Canonical identifier (e.g., "youtube:///dQw4w9WgXcQ")
    original_source: str  # User input (e.g., "https://youtube.com/watch?v=dQw4w9WgXcQ")
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentData(BaseModel):
    """
    Extracted content. Replaces all Context subclasses.
    """
    source_type: SourceType
    text: str  # The actual content (transcript, article text, file contents)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnrichedData(BaseModel):
    """
    AI-generated enrichments. Replaces all SyntheticData subclasses.
    """
    source_type: SourceType
    title: str = ""
    description: str = ""
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ProcessedContent(BaseModel):
    """
    Final aggregate - main output of Siphon pipeline.
    """
    source: SourceInfo
    content: ContentData
    enrichment: EnrichedData
    tags: list[str] = Field(default_factory=list)
    created_at: int
    updated_at: int
    
    # Convenience properties
    @property
    def id(self) -> str:
        return self.source.uri
    
    @property
    def title(self) -> str:
        return self.enrichment.title
    
    @property
    def summary(self) -> str:
        return self.enrichment.summary
```

```python
# siphon-api/src/siphon_api/interfaces.py
from typing import Protocol
from .models import SourceInfo, ContentData

class ParserStrategy(Protocol):
    """Interface for source parsing strategies"""
    def can_handle(self, source: str) -> bool: ...
    def parse(self, source: str) -> SourceInfo: ...


class ExtractorStrategy(Protocol):
    """Interface for content extraction strategies"""
    def extract(self, source: SourceInfo) -> ContentData: ...
```

```python
# siphon-api/src/siphon_api/enums.py
from enum import Enum

class SourceType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXT = "text"
    DOC = "doc"
    ARTICLE = "article"
    YOUTUBE = "youtube"
    GITHUB = "github"
    REDDIT = "reddit"
    OBSIDIAN = "obsidian"
    DRIVE = "drive"
    EMAIL = "email"
```

### siphon-server Package (Detailed)

```python
# siphon-server/src/siphon_server/core/pipeline.py
from siphon_api.models import ProcessedContent, SourceInfo, ContentData, EnrichedData
from siphon_api.interfaces import ParserStrategy, ExtractorStrategy
from .cache import CacheService
from .enrichment import ContentEnricher
import time

class SourceParser:
    """Step 1: Parse source string → SourceInfo"""
    def __init__(self, strategies: list[ParserStrategy]):
        self.strategies = strategies
    
    def execute(self, source: str) -> SourceInfo:
        for strategy in self.strategies:
            if strategy.can_handle(source):
                return strategy.parse(source)
        raise ValueError(f"No parser found for source: {source}")


class ContentExtractor:
    """Step 2: SourceInfo → ContentData"""
    def __init__(self, extractors: dict[SourceType, ExtractorStrategy]):
        self.extractors = extractors
    
    def execute(self, source: SourceInfo) -> ContentData:
        extractor = self.extractors.get(source.source_type)
        if not extractor:
            raise ValueError(f"No extractor for {source.source_type}")
        return extractor.extract(source)


class SiphonPipeline:
    """
    Main orchestrator - the aggregate root.
    Explicit pipeline: source → parse → extract → enrich → result
    """
    def __init__(
        self,
        parser: SourceParser,
        extractor: ContentExtractor,
        enricher: ContentEnricher,
        cache: CacheService | None = None,
    ):
        self.parser = parser
        self.extractor = extractor
        self.enricher = enricher
        self.cache = cache
    
    def process(self, source: str, use_cache: bool = True) -> ProcessedContent:
        # Step 1: Parse source
        source_info = self.parser.execute(source)
        
        # Check cache
        if use_cache and self.cache:
            cached = self.cache.get(source_info.uri)
            if cached:
                return cached
        
        # Step 2: Extract content
        content_data = self.extractor.execute(source_info)
        
        # Step 3: Enrich with LLM
        enriched_data = self.enricher.execute(content_data)
        
        # Step 4: Assemble result
        result = ProcessedContent(
            source=source_info,
            content=content_data,
            enrichment=enriched_data,
            tags=[],
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )
        
        # Cache
        if use_cache and self.cache:
            self.cache.set(source_info.uri, result)
        
        return result
```

```python
# siphon-server/src/siphon_server/sources/youtube/domain/parser.py
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo, SourceType
import re

class YouTubeParser(ParserStrategy):
    """YouTube bounded context - parsing logic"""
    
    def can_handle(self, source: str) -> bool:
        patterns = [
            r'youtube\.com/watch\?v=',
            r'youtu\.be/',
        ]
        return any(re.search(p, source) for p in patterns)
    
    def parse(self, source: str) -> SourceInfo:
        video_id = self._extract_video_id(source)
        
        return SourceInfo(
            source_type=SourceType.YOUTUBE,
            uri=f"youtube:///{video_id}",
            original_source=source,
            metadata={"video_id": video_id}
        )
    
    def _extract_video_id(self, url: str) -> str:
        # Regex to extract video ID
        patterns = [
            r'youtube\.com/watch\?v=([^&]+)',
            r'youtu\.be/([^?]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError(f"Cannot extract video ID from: {url}")
```

```python
# siphon-server/src/siphon_server/sources/youtube/domain/extractor.py
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from ..infrastructure.yt_dlp_client import YtDlpClient

class YouTubeExtractor(ExtractorStrategy):
    """YouTube bounded context - extraction logic"""
    
    def __init__(self, client: YtDlpClient):
        self.client = client
    
    def extract(self, source: SourceInfo) -> ContentData:
        video_id = source.metadata["video_id"]
        
        # Get transcript and metadata via infrastructure
        transcript, metadata = self.client.get_transcript(video_id)
        
        return ContentData(
            source_type=source.source_type,
            text=transcript,
            metadata=metadata
        )
```

```python
# siphon-server/src/siphon_server/api/app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from siphon_api.models import ProcessedContent
from ..core.pipeline import SiphonPipeline
from .dependencies import get_pipeline

app = FastAPI(title="Siphon Server", version="2.0.0")


class ProcessRequest(BaseModel):
    source: str
    use_cache: bool = True
    model: str = "gpt-4o"


@app.post("/api/v2/process", response_model=ProcessedContent)
async def process_content(request: ProcessRequest) -> ProcessedContent:
    """Main endpoint - process any source"""
    try:
        pipeline = get_pipeline()
        result = pipeline.process(
            source=request.source,
            use_cache=request.use_cache,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log error
        raise HTTPException(status_code=500, detail="Processing failed")


@app.get("/api/v2/cache/{uri:path}", response_model=ProcessedContent)
async def get_cached(uri: str) -> ProcessedContent:
    """Retrieve from cache"""
    pipeline = get_pipeline()
    result = pipeline.cache.get(uri) if pipeline.cache else None
    if not result:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### siphon-client Package (Detailed)

```python
# siphon-client/src/siphon_client/client.py
import httpx
from siphon_api.models import ProcessedContent
from typing import Literal

class SiphonClient:
    """
    Thin HTTP client - all processing happens server-side.
    This class is just a convenient wrapper around HTTP calls.
    """
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 300.0,  # 5 min for heavy processing
    ):
        self.base_url = base_url
        self.client = httpx.Client(timeout=timeout)
    
    def process(
        self,
        source: str,
        use_cache: bool = True,
        model: str = "gpt-4o"
    ) -> ProcessedContent:
        """
        Main method - send source to server, get ProcessedContent back.
        """
        response = self.client.post(
            f"{self.base_url}/api/v2/process",
            json={
                "source": source,
                "use_cache": use_cache,
                "model": model,
            }
        )
        response.raise_for_status()
        return ProcessedContent.model_validate(response.json())
    
    def get_cached(self, uri: str) -> ProcessedContent | None:
        """Fetch from server cache"""
        response = self.client.get(f"{self.base_url}/api/v2/cache/{uri}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return ProcessedContent.model_validate(response.json())
    
    def query(
        self,
        source_type: str | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[ProcessedContent]:
        """Query for content matching criteria"""
        params = {
            "source_type": source_type,
            "tags": tags,
            "since": since,
            "limit": limit,
        }
        response = self.client.get(
            f"{self.base_url}/api/v2/query",
            params={k: v for k, v in params.items() if v is not None}
        )
        response.raise_for_status()
        return [ProcessedContent.model_validate(item) for item in response.json()]
```

```python
# siphon-client/src/siphon_client/collections/collection.py
from typing import Callable, TypeVar, Generic
from siphon_api.models import ProcessedContent
from ..client import SiphonClient

T = TypeVar('T')

class Collection(Generic[T]):
    """
    Monadic collection for chaining operations.
    Inspired by pandas, LINQ, and functional programming.
    """
    def __init__(self, items: list[T], client: SiphonClient):
        self._items = items
        self._client = client
    
    def map(self, fn: Callable[[T], T]) -> 'Collection[T]':
        """Functor: transform each item"""
        return Collection([fn(item) for item in self._items], self._client)
    
    def flatmap(self, fn: Callable[[T], 'Collection[T]']) -> 'Collection[T]':
        """Monad: transform and flatten"""
        result = []
        for item in self._items:
            result.extend(fn(item)._items)
        return Collection(result, self._client)
    
    def filter(self, predicate: Callable[[T], bool]) -> 'Collection[T]':
        """Keep items matching predicate"""
        return Collection([item for item in self._items if predicate(item)], self._client)
    
    def expand(self, query: str) -> 'Collection[ProcessedContent]':
        """
        Semantic expansion - find related content.
        This makes a server call for semantic search.
        """
        uris = [item.id for item in self._items]
        related = self._client.find_related(uris, query)
        return Collection(related, self._client)
    
    def group_by(self, key: Callable[[T], str]) -> dict[str, 'Collection[T]']:
        """Group items by key function"""
        groups: dict[str, list[T]] = {}
        for item in self._items:
            k = key(item)
            if k not in groups:
                groups[k] = []
            groups[k].append(item)
        return {k: Collection(v, self._client) for k, v in groups.items()}
    
    # Terminal operations
    def to_list(self) -> list[T]:
        return self._items
    
    def count(self) -> int:
        return len(self._items)
    
    def first(self) -> T | None:
        return self._items[0] if self._items else None
    
    def take(self, n: int) -> 'Collection[T]':
        return Collection(self._items[:n], self._client)


# Usage example
"""
from siphon_client import SiphonClient, Collection

client = SiphonClient()

# Query and transform
results = (
    Collection(client.query(source_type="youtube", since="7d"), client)
    .filter(lambda c: "AI" in c.enrichment.topics)
    .map(lambda c: c.enrichment.summary)
    .take(10)
    .to_list()
)

# Semantic expansion
ml_content = (
    Collection(client.query(tags=["research"]), client)
    .expand("machine learning")  # Server-side semantic search
    .group_by(lambda c: c.source.source_type)
)
"""
```

```python
# siphon-client/src/siphon_client/cli.py
import click
from .client import SiphonClient
from .display import display_content

@click.group()
def cli():
    """Siphon CLI - Universal content ingestion"""
    pass

@cli.command()
@click.argument('source')
@click.option('--no-cache', is_flag=True, help='Skip cache')
@click.option('--server', default='http://localhost:8000', help='Server URL')
def process(source: str, no_cache: bool, server: str):
    """Process a source (file, URL, etc.)"""
    client = SiphonClient(base_url=server)
    result = client.process(source, use_cache=not no_cache)
    display_content(result)

@cli.command()
@click.option('--source-type', help='Filter by source type')
@click.option('--tags', help='Filter by tags (comma-separated)')
@click.option('--since', help='Filter by date (e.g., 7d, 2024-01-01)')
@click.option('--server', default='http://localhost:8000')
def query(source_type: str, tags: str, since: str, server: str):
    """Query stored content"""
    client = SiphonClient(base_url=server)
    tag_list = tags.split(',') if tags else None
    results = client.query(source_type=source_type, tags=tag_list, since=since)
    
    for result in results:
        display_content(result)
        click.echo("\n" + "="*80 + "\n")

if __name__ == '__main__':
    cli()
```

---

## Core Data Models

### Philosophy: Flat Over Hierarchical

Instead of 11 subclasses per abstraction, use **4 flat models** with metadata dicts.

```python
# OLD (33 classes)
YouTubeURI → YouTubeContext → YouTubeSyntheticData
AudioURI → AudioContext → AudioSyntheticData
# ... 11 sets of 3 classes

# NEW (4 classes)
SourceInfo (metadata: {...})
ContentData (metadata: {...})
EnrichedData
ProcessedContent
```

### Trade-off: Type Safety vs Flexibility

**Loss:** Compile-time guarantees on metadata fields  
**Gain:** Can add fields without class changes, trivial serialization

**Mitigation:** Typed accessors when needed:
```python
class ContentData(BaseModel):
    # ...
    
    @property
    def youtube_metadata(self) -> YouTubeMetadata | None:
        if self.source_type == SourceType.YOUTUBE:
            return YouTubeMetadata.model_validate(self.metadata)
        return None
```

### Schema Evolution

Metadata dicts allow gradual evolution:
- v1: `{"video_id": "abc"}`
- v2: `{"video_id": "abc", "channel_id": "UC123"}`
- v3: `{"video_id": "abc", "channel_id": "UC123", "playlist": "PLxyz"}`

Old records still work, accessors handle missing fields gracefully.

---

## Pipeline Architecture

### Explicit Steps

```
Source (str)
    ↓
[SourceParser] ← Strategy pattern dispatches to YouTubeParser, AudioParser, etc.
    ↓
SourceInfo
    ↓
[ContentExtractor] ← Strategy pattern dispatches to YouTubeExtractor, AudioExtractor, etc.
    ↓
ContentData
    ↓
[ContentEnricher] ← Universal LLM enrichment
    ↓
EnrichedData
    ↓
ProcessedContent (final aggregate)
```

### Benefits

1. **Visibility:** Can see entire pipeline in `SiphonPipeline.process()`
2. **Testability:** Can mock each step independently
3. **Monitoring:** Add logging/timing around each step
4. **Extensibility:** Add steps without modifying existing code
5. **Debugging:** Know exactly which step failed

### Dependency Injection

```python
# server/dependencies.py
from sources.youtube import YouTubeParser, YouTubeExtractor, YtDlpClient
from sources.audio import AudioParser, AudioExtractor, WhisperClient

def create_pipeline() -> SiphonPipeline:
    # Wire up strategies
    parser = SourceParser(strategies=[
        YouTubeParser(),
        AudioParser(),
        # ... register all parsers
    ])
    
    extractor = ContentExtractor(extractors={
        SourceType.YOUTUBE: YouTubeExtractor(
            client=YtDlpClient()
        ),
        SourceType.AUDIO: AudioExtractor(
            client=WhisperClient(model="large-v3")
        ),
        # ... register all extractors
    })
    
    enricher = ContentEnricher(
        model="gpt-4o",
        ollama_fallback=True
    )
    
    cache = PostgresCache(
        connection_string=settings.DATABASE_URL
    )
    
    return SiphonPipeline(parser, extractor, enricher, cache)


# For testing
def create_test_pipeline(mock_extractors: dict) -> SiphonPipeline:
    parser = SourceParser(strategies=[YouTubeParser()])
    extractor = ContentExtractor(extractors=mock_extractors)
    enricher = Mock(spec=ContentEnricher)
    return SiphonPipeline(parser, extractor, enricher)
```

---

## Domain-Driven Design

### Bounded Context = Source Type

Each source type lives in its own directory with complete isolation.

```
sources/
├── youtube/          # YouTube bounded context
│   ├── domain/       # Business logic
│   │   ├── parser.py
│   │   ├── extractor.py
│   │   └── models.py       # VideoMetadata, Channel (YouTube-specific)
│   ├── infrastructure/     # External APIs
│   │   ├── yt_dlp_client.py
│   │   └── youtube_api.py
│   └── tests/
│       ├── test_parser.py
│       └── test_extractor.py
│
├── audio/            # Audio bounded context
│   ├── domain/
│   │   ├── parser.py
│   │   ├── extractor.py
│   │   └── models.py       # Speaker, TranscriptSegment (Audio-specific)
│   ├── infrastructure/
│   │   ├── whisper_client.py
│   │   └── pyannote_diarizer.py
│   └── tests/
│
└── reddit/           # New source type? Just add directory!
    ├── domain/
    ├── infrastructure/
    └── tests/
```

### Ubiquitous Language

Each context has its own vocabulary:
- **YouTube:** "video", "channel", "transcript" (captions)
- **Audio:** "speaker", "transcript" (STT), "diarization"
- **GitHub:** "repository", "commit", "pull request"

Same words, different meanings in different contexts. That's fine - they're isolated.

### Anti-Corruption Layer

Contexts communicate only through shared interfaces (from `siphon-api`):

```python
# sources/youtube/domain/parser.py
from siphon_api.interfaces import ParserStrategy  # ✅ Shared interface
from siphon_api.models import SourceInfo         # ✅ Shared models

# ❌ NO imports from sources/audio/ or sources/github/
```

### Benefits of DDD

1. **Locality of Change:** Modify YouTube without touching Audio
2. **Independent Evolution:** Add playlist support to YouTube, multi-language to Audio
3. **Team Scalability:** Different devs own different contexts
4. **Testing Isolation:** Mock only what each context needs
5. **Clear Dependencies:** Cross-context imports are immediately obvious violations

---

## Adding New Source Types

### Example: Adding Reddit Support

**Time estimate:** ~1-2 hours

### Step 1: Add Enum (1 minute)

```python
# siphon-api/src/siphon_api/enums.py
class SourceType(str, Enum):
    # ... existing ...
    REDDIT = "reddit"  # ← Add this
```

**Note:** This requires releasing a new version of `siphon-api` (bump patch version).

### Step 2: Create Bounded Context (5 minutes)

```bash
cd siphon-server/src/siphon_server/sources
mkdir -p reddit/{domain,infrastructure,tests}
touch reddit/__init__.py
touch reddit/domain/{__init__.py,parser.py,extractor.py,models.py}
touch reddit/infrastructure/{__init__.py,praw_client.py}
touch reddit/tests/{__init__.py,test_parser.py,test_extractor.py}
```

### Step 3: Define Domain Models (10 minutes)

```python
# reddit/domain/models.py
from pydantic import BaseModel

class SubredditMetadata(BaseModel):
    subreddit: str
    subscribers: int
    active_users: int

class RedditPost(BaseModel):
    post_id: str
    title: str
    author: str
    score: int
    body: str
    created_utc: int
```

### Step 4: Implement Parser (15 minutes)

```python
# reddit/domain/parser.py
from siphon_api.interfaces import ParserStrategy
from siphon_api.models import SourceInfo, SourceType
import re

class RedditParser(ParserStrategy):
    def can_handle(self, source: str) -> bool:
        return "reddit.com/r/" in source or source.startswith("r/")
    
    def parse(self, source: str) -> SourceInfo:
        subreddit = self._extract_subreddit(source)
        return SourceInfo(
            source_type=SourceType.REDDIT,
            uri=f"reddit:///{subreddit}",
            original_source=source,
            metadata={"subreddit": subreddit}
        )
    
    def _extract_subreddit(self, source: str) -> str:
        if source.startswith("r/"):
            return source[2:]
        match = re.search(r'reddit\.com/r/([\w]+)', source)
        if match:
            return match.group(1)
        raise ValueError(f"Cannot extract subreddit from: {source}")
```

### Step 5: Implement Extractor (30 minutes)

```python
# reddit/domain/extractor.py
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from ..infrastructure.praw_client import PrawClient
from .models import RedditPost

class RedditExtractor(ExtractorStrategy):
    def __init__(self, client: PrawClient):
        self.client = client
    
    def extract(self, source: SourceInfo) -> ContentData:
        subreddit = source.metadata["subreddit"]
        posts = self.client.get_hot_posts(subreddit, limit=100)
        
        text = self._format_posts(posts)
        
        return ContentData(
            source_type=source.source_type,
            text=text,
            metadata={
                "subreddit": subreddit,
                "post_count": len(posts),
                "posts": [p.model_dump() for p in posts],
            }
        )
    
    def _format_posts(self, posts: list[RedditPost]) -> str:
        lines = []
        for post in posts:
            lines.append(f"# {post.title}")
            lines.append(f"by u/{post.author} | {post.score} points")
            lines.append(f"\n{post.body}\n")
            lines.append("---\n")
        return "\n".join(lines)
```

### Step 6: Implement Infrastructure (20 minutes)

```python
# reddit/infrastructure/praw_client.py
import praw
from ..domain.models import RedditPost

class PrawClient:
    def __init__(self, client_id: str, client_secret: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="Siphon/2.0"
        )
    
    def get_hot_posts(self, subreddit: str, limit: int) -> list[RedditPost]:
        sub = self.reddit.subreddit(subreddit)
        posts = []
        for submission in sub.hot(limit=limit):
            posts.append(RedditPost(
                post_id=submission.id,
                title=submission.title,
                author=str(submission.author),
                score=submission.score,
                body=submission.selftext,
                created_utc=int(submission.created_utc),
            ))
        return posts
```

### Step 7: Register Strategies (5 minutes)

```python
# reddit/__init__.py
from .domain.parser import RedditParser
from .domain.extractor import RedditExtractor
from .infrastructure.praw_client import PrawClient

__all__ = ["RedditParser", "RedditExtractor", "PrawClient"]
```

```python
# server/api/dependencies.py
from sources.reddit import RedditParser, RedditExtractor, PrawClient

def create_pipeline() -> SiphonPipeline:
    parser = SourceParser(strategies=[
        YouTubeParser(),
        RedditParser(),  # ← Add this
        # ...
    ])
    
    extractor = ContentExtractor(extractors={
        SourceType.YOUTUBE: YouTubeExtractor(...),
        SourceType.REDDIT: RedditExtractor(  # ← Add this
            client=PrawClient(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
            )
        ),
        # ...
    })
    
    return SiphonPipeline(parser, extractor, enricher, cache)
```

### Step 8: Test (10 minutes)

```python
# reddit/tests/test_parser.py
def test_reddit_parser():
    parser = RedditParser()
    
    # Test URL format
    result = parser.parse("https://reddit.com/r/MachineLearning")
    assert result.source_type == SourceType.REDDIT
    assert result.metadata["subreddit"] == "MachineLearning"
    
    # Test shorthand format
    result = parser.parse("r/MachineLearning")
    assert result.metadata["subreddit"] == "MachineLearning"
```

### Done!

**No changes to:**
- Client code
- API models (except enum)
- Database schema
- Other source types
- Core pipeline logic

**Client usage immediately works:**
```python
from siphon_client import SiphonClient

client = SiphonClient()
result = client.process("r/MachineLearning")
print(result.summary)
```

---

## Client Collections API

### Monadic Query DSL

Inspired by pandas, LINQ, and functional programming.

```python
from siphon_client import SiphonClient, Collection

client = SiphonClient()

# Example 1: Filter and transform
summaries = (
    Collection(client.query(source_type="youtube", since="7d"), client)
    .filter(lambda c: "AI" in c.enrichment.topics)
    .map(lambda c: c.enrichment.summary)
    .take(10)
    .to_list()
)

# Example 2: Group and aggregate
by_type = (
    Collection(client.query(tags=["research"]), client)
    .group_by(lambda c: c.source.source_type)
)
for source_type, items in by_type.items():
    print(f"{source_type}: {items.count()} items")

# Example 3: Semantic expansion (server-side search)
related = (
    Collection(client.query(source_type="article"), client)
    .expand("machine learning")  # Semantic search via server
    .filter(lambda c: c.created_at > some_timestamp)
    .to_list()
)

# Example 4: Flatmap for hierarchical data
all_topics = (
    Collection(client.query(source_type="youtube"), client)
    .flatmap(lambda c: Collection(c.enrichment.topics, client))
    .to_list()
)
```

### Operations

**Functor operations:**
- `map(fn)` - Transform each item
- `filter(predicate)` - Keep matching items
- `take(n)` - Take first n items

**Monad operations:**
- `flatmap(fn)` - Transform and flatten

**Aggregation:**
- `group_by(key_fn)` - Group items by key
- `count()` - Count items
- `first()` - Get first item

**Server-side operations:**
- `expand(query)` - Semantic search for related content

**Terminal operations:**
- `to_list()` - Materialize to list
- `to_df()` - Convert to pandas DataFrame (if pandas installed)

---

## Server API Endpoints

### REST API (FastAPI)

```
POST   /api/v2/process
GET    /api/v2/cache/{uri}
DELETE /api/v2/cache/{uri}
GET    /api/v2/query
POST   /api/v2/search/semantic
GET    /health
GET    /docs  (Swagger UI)
```

### POST /api/v2/process

**Request:**
```json
{
  "source": "https://youtube.com/watch?v=abc123",
  "use_cache": true,
  "model": "gpt-4o"
}
```

**Response:**
```json
{
  "source": {
    "source_type": "youtube",
    "uri": "youtube:///abc123",
    "original_source": "https://youtube.com/watch?v=abc123",
    "metadata": {"video_id": "abc123"}
  },
  "content": {
    "source_type": "youtube",
    "text": "Transcript here...",
    "metadata": {"channel": "Lex Fridman", "duration": 3600}
  },
  "enrichment": {
    "source_type": "youtube",
    "title": "Interview with...",
    "description": "...",
    "summary": "...",
    "topics": ["AI", "philosophy"],
    "entities": ["Lex Fridman", "Guest Name"]
  },
  "tags": [],
  "created_at": 1729814400,
  "updated_at": 1729814400
}
```

### GET /api/v2/query

**Request:**
```
GET /api/v2/query?source_type=youtube&tags=AI,research&since=7d&limit=50
```

**Response:**
```json
[
  {/* ProcessedContent 1 */},
  {/* ProcessedContent 2 */},
  ...
]
```

### POST /api/v2/search/semantic

**Request:**
```json
{
  "query": "machine learning papers about transformers",
  "source_types": ["article", "github"],
  "limit": 20
}
```

**Response:**
```json
{
  "results": [
    {
      "content": {/* ProcessedContent */},
      "score": 0.95
    },
    ...
  ]
}
```

---

## Deployment Architecture

### Hardware Requirements

**Server (siphon-server):**
- GPU: NVIDIA RTX 5090 (required for Whisper large-v3)
- RAM: 32GB+ (for LLM inference)
- Storage: 500GB+ SSD (for model weights + cache)
- OS: Ubuntu 22.04+ with CUDA 12.x drivers
- Python: 3.12+

**Client (siphon-client):**
- Any machine (Mac, Linux, Windows, mobile)
- Python: 3.10+
- RAM: 1GB (just for HTTP client)
- No GPU required

### Network Topology

```
┌──────────────┐
│   Client 1   │ (Mac laptop)
│ siphon-client│
└───────┬──────┘
        │
        │ HTTP
        │
┌───────▼──────┐     ┌──────────────┐
│   Client 2   │────▶│ siphon-server│◀────┐
│ siphon-client│     │   (FastAPI)  │     │
└──────────────┘     │              │     │
                     │  ML Server   │     │
┌──────────────┐     │  RTX 5090    │     │
│   Client N   │────▶│              │     │
│ siphon-client│     └──────┬───────┘     │
└──────────────┘            │             │
                            │             │
                     ┌──────▼──────┐      │
                     │  Postgres   │      │
                     │  + pgvector │      │
                     └─────────────┘      │
                                          │
                     ┌────────────────────┘
                     │
              ┌──────▼──────┐
              │  Chroma DB  │
              │  (optional) │
              └─────────────┘
```

### Docker Deployment

```yaml
# docker-compose.yml (for server)
version: '3.8'

services:
  siphon-server:
    build: ./siphon-server
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/siphon
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./models:/models  # Model weights cache
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    depends_on:
      - postgres
      - redis
  
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=siphon
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  pgdata:
  redis_data:
```

### Client Installation

```bash
# On any machine (Mac, Linux, Windows)
pip install siphon-client

# Configure server URL
export SIPHON_SERVER_URL="http://ml-server.local:8000"

# Use it
siphon process "https://youtube.com/watch?v=abc123"
```

### Package Distribution

```
PyPI:
  ├─ siphon-api (v2.0.0)        # Shared models
  ├─ siphon-server (v2.0.0)     # Server + all extractors
  └─ siphon-client (v2.0.0)     # Client SDK
```

**Version compatibility:**
- Client v2.x.x works with Server v2.x.x
- API changes require major version bump
- Backward compatibility within major version

---

## Migration Strategy

### Phase 1: Build New System Alongside Old (Week 1-2)

**Goal:** New architecture exists but old system still works

1. Create three new package directories
2. Build `siphon-api` with 4 flat models
3. Build `SiphonPipeline` in `siphon-server`
4. Implement strategies for 3 source types (YouTube, Audio, Text)
5. Build thin `SiphonClient`
6. Add FastAPI endpoints
7. Write integration tests

**Deliverable:** New system processes YouTube, Audio, Text. Old system still handles everything.

### Phase 2: Migrate Extractors (Week 3-4)

**Goal:** Port existing extraction logic to new strategies

For each source type:
1. Create bounded context directory
2. Move existing logic to domain/extractor
3. Wrap external APIs in infrastructure layer
4. Add tests
5. Register in pipeline

**Order:**
1. YouTube (already done in Phase 1)
2. Audio (already done in Phase 1)
3. Text (already done in Phase 1)
4. Article
5. GitHub
6. Doc (PDF, DOCX, etc.)
7. Image
8. Video
9. Drive
10. Email
11. Obsidian

**Deliverable:** All source types work in new system.

### Phase 3: Update Client Code (Week 5)

**Goal:** CLI and integrations use new client

1. Modify CLI to use `SiphonClient` instead of direct pipeline
2. Update Obsidian plugin (if exists)
3. Update any scripts or notebooks
4. Test thoroughly
5. Keep old code as fallback

**Deliverable:** All user-facing interfaces use new system.

### Phase 4: Delete Old Architecture (Week 6)

**Goal:** Remove technical debt

1. Delete URI subclasses (11 files)
2. Delete Context subclasses (11 files)
3. Delete SyntheticData subclasses (11 files)
4. Delete factory methods
5. Clean up imports
6. Update tests
7. Update documentation

**Deliverable:** Clean codebase, 33 fewer classes.

### Phase 5: Database Migration (Week 7)

**Goal:** Update schema to match new models

1. Write migration script to transform old records
2. Add `schema_version` column
3. Run migration on dev database
4. Verify data integrity
5. Run migration on production
6. Keep old tables for rollback

**Deliverable:** Database matches new schema.

### Phase 6: Deploy & Monitor (Week 8)

**Goal:** Production deployment

1. Deploy server to ML box
2. Deploy client to dev machines
3. Monitor for errors
4. Collect metrics (latency, cache hit rate, etc.)
5. Optimize hot paths
6. Document deployment process

**Deliverable:** Production system running new architecture.

---

## Trade-offs & Design Decisions

### 1. Metadata Dicts vs Typed Classes

**Decision:** Use `dict[str, Any]` for source-specific metadata

**Trade-off:**
- ✅ Flexibility: Add fields without class changes
- ✅ Serialization: Trivial JSON encoding
- ❌ Type safety: No compile-time checks on metadata fields

**Mitigation:**
```python
class ContentData(BaseModel):
    # Core fields with types
    source_type: SourceType
    text: str
    
    # Flexible metadata
    metadata: dict[str, Any] = {}
    
    # Typed accessors when needed
    @property
    def youtube_metadata(self) -> YouTubeMetadata | None:
        if self.source_type == SourceType.YOUTUBE:
            return YouTubeMetadata.model_validate(self.metadata)
        return None
```

### 2. Strategy Pattern vs Registry Pattern

**Decision:** Use strategy pattern with list of strategies

**Trade-off:**
- ✅ Flexible: Can implement chain-of-responsibility
- ✅ Extensible: Add strategies without registry
- ❌ Performance: O(n) scan to find handler

**Mitigation:** Use dict for extractors (O(1) lookup by SourceType)

### 3. Three Packages vs Monorepo

**Decision:** Three separate packages

**Trade-off:**
- ✅ Dependency isolation: Client doesn't need GPU libs
- ✅ Deployment flexibility: Server on ML box, client anywhere
- ✅ Clear boundaries: Can't accidentally import across packages
- ❌ Coordination: Must version and publish three packages
- ❌ Duplication: Some code might be duplicated

**Mitigation:** Use monorepo tool (e.g., `pants`, `bazel`) for coordinated releases

### 4. DDD Bounded Contexts vs Flat Structure

**Decision:** One directory per source type (DDD)

**Trade-off:**
- ✅ Locality: All YouTube code in sources/youtube/
- ✅ Isolation: Changes don't affect other sources
- ✅ Clarity: Know exactly where code lives
- ❌ Verbosity: More directories and files
- ❌ Overhead: Must understand DDD concepts

**Assessment:** Benefits outweigh costs for 11+ source types.

### 5. Synchronous vs Async Pipeline

**Decision:** Synchronous pipeline (for now)

**Trade-off:**
- ✅ Simplicity: Easier to reason about
- ✅ Debugging: Stack traces are clear
- ❌ Performance: Can't parallelize steps

**Future:** Add async version when parallelization is needed:
```python
class AsyncSiphonPipeline:
    async def process(self, sources: list[str]) -> list[ProcessedContent]:
        tasks = [self._process_one(source) for source in sources]
        return await asyncio.gather(*tasks)
```

### 6. Server-Side Enrichment vs Client-Side

**Decision:** All enrichment happens server-side

**Trade-off:**
- ✅ Consistency: Same model for all clients
- ✅ Performance: GPU stays on server
- ✅ Caching: Enrichments cached centrally
- ❌ Latency: Client must wait for network + LLM
- ❌ Flexibility: Can't use local models

**Mitigation:** Add `enrich_locally` flag if needed (future)

### 7. Postgres vs MongoDB for Storage

**Decision:** Postgres with JSONB columns

**Trade-off:**
- ✅ JSONB: Flexible schema for metadata
- ✅ pgvector: Built-in vector search
- ✅ ACID: Reliable transactions
- ✅ Familiarity: Team knows Postgres
- ❌ Scaling: Vertical scaling primarily

**Alternative:** Add MongoDB/DynamoDB for metadata if Postgres becomes bottleneck

### 8. REST vs GraphQL

**Decision:** REST API (for now)

**Trade-off:**
- ✅ Simplicity: Well-understood
- ✅ Tooling: OpenAPI/Swagger
- ✅ Caching: HTTP caching works
- ❌ Overfetching: Client gets full ProcessedContent
- ❌ Flexibility: Fixed endpoints

**Future:** Add GraphQL endpoint if clients need selective field fetching

---

## Future Roadmap

### Short Term (Q1 2025)

1. **Complete Migration**
   - Finish porting all 11 source types
   - Deploy to production
   - Sunset old architecture

2. **Performance Optimization**
   - Profile hot paths
   - Add Redis caching layer
   - Optimize LLM calls (batching)

3. **Monitoring & Observability**
   - Add structured logging
   - Set up Grafana dashboards
   - Alert on failures

### Medium Term (Q2-Q3 2025)

1. **New Source Types**
   - RSS feeds (monitor blogs/podcasts)
   - Email (Gmail/Outlook integration)
   - Twitter/X threads
   - Slack channels
   - Discord servers

2. **Advanced Collections**
   - Saved collections (persist queries)
   - Collection snapshots (point-in-time views)
   - Collection sharing (public URLs)
   - Collection export (PDF, DOCX)

3. **Vector Search**
   - Semantic search across all content
   - "Find similar" feature
   - Embedding model selection
   - Reranking

4. **Real-time Monitoring**
   - Daemon to monitor RSS feeds
   - Webhook support for live updates
   - Email notifications for new content

### Long Term (Q4 2025 - 2026)

1. **Multi-Modal Analysis**
   - Extract images from videos
   - Analyze charts/graphs in PDFs
   - Optical character recognition (OCR)
   - Speaker identification in audio

2. **Web UI**
   - React frontend for siphon-client
   - Visual query builder
   - Content browser
   - Settings/configuration

3. **Mobile Apps**
   - iOS app (Swift)
   - Android app (Kotlin)
   - Share to Siphon from any app

4. **Collaboration Features**
   - Multi-user support
   - Shared collections
   - Comments/annotations
   - Team workspaces

5. **Advanced LLM Features**
   - Custom prompts per source type
   - Chain-of-thought reasoning
   - Multi-turn enrichment
   - Fact-checking/verification

6. **Enterprise Features**
   - SSO/SAML authentication
   - Role-based access control
   - Audit logs
   - SLA guarantees
   - On-premise deployment

---

## Appendix A: File Checklist

### siphon-api Package

- [ ] `pyproject.toml` - Package metadata, dependencies
- [ ] `src/siphon_api/__init__.py` - Package exports
- [ ] `src/siphon_api/models.py` - Core DTOs (4 classes)
- [ ] `src/siphon_api/interfaces.py` - Strategy protocols
- [ ] `src/siphon_api/enums.py` - SourceType enum
- [ ] `tests/test_models.py` - Model validation tests
- [ ] `README.md` - Usage documentation
- [ ] `CHANGELOG.md` - Version history

### siphon-server Package

- [ ] `pyproject.toml` - Dependencies (torch, whisper, etc.)
- [ ] `src/siphon_server/__init__.py`
- [ ] `src/siphon_server/core/pipeline.py` - SiphonPipeline
- [ ] `src/siphon_server/core/cache.py` - CacheService
- [ ] `src/siphon_server/core/enrichment.py` - ContentEnricher
- [ ] `src/siphon_server/sources/youtube/domain/parser.py`
- [ ] `src/siphon_server/sources/youtube/domain/extractor.py`
- [ ] ... (repeat for all 11 source types)
- [ ] `src/siphon_server/api/app.py` - FastAPI app
- [ ] `src/siphon_server/api/routes.py` - API endpoints
- [ ] `src/siphon_server/api/dependencies.py` - DI container
- [ ] `tests/unit/` - Unit tests per bounded context
- [ ] `tests/integration/` - End-to-end tests
- [ ] `docker-compose.yml` - Docker deployment
- [ ] `README.md` - Deployment guide

### siphon-client Package

- [ ] `pyproject.toml` - Dependencies (httpx, rich)
- [ ] `src/siphon_client/__init__.py`
- [ ] `src/siphon_client/client.py` - SiphonClient class
- [ ] `src/siphon_client/collections/collection.py` - Monadic DSL
- [ ] `src/siphon_client/display.py` - Rich formatting
- [ ] `src/siphon_client/cli.py` - Click CLI
- [ ] `tests/test_client.py` - Client tests (mocked server)
- [ ] `tests/test_collections.py` - Collection DSL tests
- [ ] `README.md` - Client usage guide

---

## Appendix B: Key Metrics

### Performance Targets

- **Cache hit rate:** >80%
- **Processing latency:**
  - YouTube (5min video): <30s
  - Audio (1hr podcast): <90s
  - PDF (50 pages): <15s
  - Article (5000 words): <10s
- **API response time:** <200ms (cached), <5s (cold)
- **Concurrent requests:** 10+ simultaneous processing jobs

### Quality Metrics

- **Test coverage:** >80%
- **Type coverage:** >90% (mypy strict)
- **Documentation:** All public APIs documented
- **Code duplication:** <5%

---

## Conclusion

This refactor transforms Siphon from a monolithic, tightly-coupled system into a clean, three-package architecture:

1. **siphon-api** - Shared contracts (4 flat DTOs, ~200 LOC)
2. **siphon-server** - Processing pipeline (DDD, bounded contexts)
3. **siphon-client** - Thin HTTP wrapper (collections DSL)

**Key improvements:**
- 33 classes → 4 DTOs (92% reduction)
- Explicit pipeline (testable, debuggable)
- Clear separation (server on ML box, client anywhere)
- DDD structure (isolated bounded contexts)
- ~1 hour to add new source types

**Next steps:**
1. Review this design with team
2. Build Phase 1 spike (YouTube + Audio + Text)
3. Validate approach
4. Execute migration plan
5. Ship v2.0

The new architecture is simpler, more maintainable, and easier to extend. Ready to build?
