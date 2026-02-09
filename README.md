Siphon is a multi-modal content ingestion and enrichment framework designed to transform unstructured input—including URLs (YouTube, generic web articles, Google Drive) and local files (PDFs, audio, source code, data)—into structured, LLM-ready context. The system is partitioned into three discrete packages: `siphon-api` for data contracts and protocols, `siphon_server` for orchestration and persistence, and `siphon_client` for CLI-driven consumption and monadic collection manipulation.

The core architecture utilizes a strategy-based pipeline managed by the `SiphonPipeline` orchestrator. The process follows a strictly defined lifecycle: a `ParserStrategy` resolves input strings into a canonical `SourceInfo` URI; an `ExtractorStrategy` retrieves raw text and metadata; and an `EnricherStrategy` generates high-density semantic descriptions and summaries via asynchronous LLM integration. The final output is a `ProcessedContent` aggregate, which is persisted in a PostgreSQL backend using SQLAlchemy ORM for long-term retrieval and caching.

### Technical Phases and Component Interaction

1.  **Parsing:** The `SourceParser` iterates through a dynamically loaded registry of strategies (YouTube, Article, Doc, Audio, Drive). It normalizes URLs (removing tracking parameters, resolving IDNA/punycode) or computes SHA-256 hashes for local files to generate immutable URIs (e.g., `youtube:///video_id` or `doc:///extension/hash`).
2.  **Extraction:** Content extraction is delegated to domain-specific libraries. `yt-dlp` and `youtube-transcript-api` handle video metadata and transcripts; `readabilipy` and `markdownify` process HTML articles; and Microsoft's `MarkItDown` handles office documents and PDFs. Audio extraction utilizes a multi-stage sub-pipeline involving `pydub` for WAV normalization and `openai/whisper-base` for transcription.
3.  **Enrichment:** This phase uses the `Conduit` LLM wrapper to perform concurrent asynchronous queries. It renders Jinja2 templates for source-specific prompts (e.g., `code_description.jinja2`, `audio_summary.jinja2`) to generate semantic descriptions optimized for vector similarity search and human-readable executive summaries.
4.  **Persistence:** The `ContentRepository` provides a transactional interface to PostgreSQL. It supports idempotent operations through URI-based lookups, preventing redundant LLM enrichment and extraction for previously processed content.

### Implementation Details

*   **Concurrency Model:** The server leverages `asyncio` for non-blocking I/O during LLM enrichment. Heavy ML workloads, specifically speaker diarization (`pyannote/audio`) and image generation (`flux`, `z-image`), are decoupled into isolated Docker-sidecar microservices. This prevents the main server from inheriting massive CUDA/PyTorch dependency stacks and allows for independent scaling of GPU-bound tasks.
*   **Data Flow:** Transport objects are defined using Pydantic. `SiphonFile` handles raw byte payloads by base64-encoding data for JSON compatibility while maintaining mandatory SHA-256 checksum verification to ensure integrity across the network boundary.
*   **Caching Strategy:** Siphon implements a multi-tier caching system. A primary PostgreSQL database stores the final `ProcessedContent` aggregate. Secondary SQLite-backed caches (`YouTubeTranscriptCache`, `ArticleCache`) store intermediate raw data to mitigate rate-limiting on external APIs and reduce latency for repeated extractions.
*   **Worker Isolation:** The diarization and image generation workers use a launcher utility that manages the lifecycle of containerized sidecars. Communication is handled via internal HTTP calls to FastAPI endpoints within the containers, ensuring the host process remains lightweight.

### Rationale and Technical Context

*   **Strategy vs. Monolith:** The strategy pattern was chosen to allow new source types to be added by implementing three specific protocols (`Parser`, `Extractor`, `Enricher`) without modifying the core `SiphonPipeline` orchestrator.
*   **Protocol-based URIs:** The use of canonical URIs (e.g., `article:///sha256/hash`) decouples the identity of the content from its original source URL, allowing for deduplication when the same content is accessed via different mirrors or normalized URL variations.
*   **Worker Decoupling:** Previous iterations attempted to run `pyannote` and `whisper` within the main process, resulting in severe library version conflicts and excessive memory consumption. The current sidecar architecture isolates these environments, allowing for specific optimizations like Flash Attention or 8-bit quantization without affecting the main server.

### Operational Context and Limitations

*   **Dependencies:** The system requires a PostgreSQL instance. Local file processing assumes a shared or local filesystem accessible to the server. ML workers require NVIDIA GPUs with appropriate VRAM (8GB+ for diarization, 16GB-32GB+ for Flux/HiDream image generation).
*   **Footguns:** Local file ingestion uses absolute paths; moving files after ingestion breaks the `FILE_PATH` origin logic in the `SiphonRequest`. The `SourceParser` uses a 16-character truncation of SHA-256 for URI construction; while collisions are statistically improbable for typical document collections, it is a non-standard hash length.
*   **Operational Requirements:** The `diarization_service` requires a `HUGGINGFACEHUB_API_TOKEN` with access to the `pyannote/speaker-diarization-3.1` model. YouTube extraction relies on proxies (Webshare) to avoid IP-based rate limiting during high-volume transcript retrieval.
