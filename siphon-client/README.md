# siphon-client

CLI and high-level client wrappers for the Siphon content pipeline. Installs the `siphon` command and provides `SiphonClient` for programmatic access.

## Commands

| Command | Purpose |
| :--- | :--- |
| `gulp` | Process a source and persist to the database |
| `extract` | Extract content without persisting (ephemeral) |
| `enrich` | Run LLM enrichment without persisting (ephemeral) |
| `parse` | Resolve a source to its canonical URI |
| `query` | Search the content database |
| `results` | Recall and manage query history |
| `inspect` | Show the most recent enrichment run for a URI |
| `traverse` | Walk the wikilink graph from a node |
| `sync` | Sync an Obsidian vault into Siphon |
| `bulk-extract` | Batch-extract raw text from multiple sources |

Run `siphon <command> --help` for full options on any subcommand.

## Retrieval

### Modes

`siphon query` supports five search modes selected via `--mode` (or `-m`):

| Mode | Backing | Description |
| :--- | :--- | :--- |
| `hybrid` (default) | `repository.search_hybrid` | RRF fusion of BM25 + semantic |
| `semantic` | `repository.search_semantic` | Vector-only via HNSW + cosine |
| `fts` | `repository.search_fts` | BM25 via `ts_rank_cd` over `fts_doc` |
| `sql` | `repository.search_by_text` | Legacy ILIKE on title and description |
| `fuzzy` | (reserved) | Not implemented |

#### When to use which

- **`hybrid`** is the right default. RRF combines BM25 ordering and semantic ordering without requiring score calibration, and tolerates one signal being noisy.
- **`semantic`** when the query is conceptual ("retrieval-augmented generation eval methods") and lexical noise would hurt.
- **`fts`** for exact-entity, quote, or number queries ("Q3 2025 revenue 585M") where vector retrieval drifts.
- **`sql`** as a quick title-substring lookup. Kept for backwards compatibility.

### HyDE

`hybrid` and `semantic` modes run HyDE (Hypothetical Document Embeddings, Gao et al. 2022) by default. The flow:

1. The raw query is sent to gpt-oss on bywater.
2. gpt-oss writes a passage that would answer the query.
3. The passage is embedded with nomic-embed-text-v1.5.
4. That embedding is what the vector search actually queries against.

This works because Siphon's stored descriptions are also written in answer-voice (via the HyDE description guidelines per source type). Matching answer-shaped query embeddings to answer-shaped corpus embeddings lands in better semantic territory than matching question-shaped queries.

Disable per call with `--no-hyde`:

```bash
siphon query "react useState" --no-hyde -n 3
```

Faster (no LLM call upfront, ~1-3s saved), lower quality on conversational queries. Use it when you know the query is already keyword-shaped.

### Filters

Three orthogonal filters work across all modes:

```bash
siphon query "RAG"       --type youtube         # by source type
siphon query "tax"       --extension pdf        # by file extension (doc only)
siphon query "policy"    --date ">2024-06-01"   # by date
```

For non-sql modes, filters are post-applied (we over-fetch from the index and then trim), so a restrictive filter may undercount. Bump `--limit` accordingly.

### Output formats (`-r` / `--return-type`)

| Code | Returns |
| :--- | :--- |
| `t` (default) | title |
| `s` | summary |
| `d` | description |
| `c` | content (raw text) |
| `m` | metadata (JSON) |
| `u` | original source URL |
| `id` | URI |
| `st` | source type |
| `json` | full ProcessedContent JSON |

Single-result outputs go to stdout cleanly (raw), so they pipe well:

```bash
siphon query --latest -r c | wc -w
siphon query --type youtube -n 1 -r json | jq .enrichment.topics
```

### Examples

```bash
# Hybrid retrieval, default tuning
siphon query "claude code subagents"

# Vector-only with HyDE
siphon query "ECW cliff routing" --mode semantic

# BM25 for exact entity matches
siphon query "Q3 2025 revenue" --mode fts

# Skip HyDE on a keyword-shaped query
siphon query "useState useEffect" --no-hyde

# Source type filter on hybrid
siphon query "agent orchestration" --type youtube -n 5

# Get full JSON of the top result
siphon query "headwater routing" -n 1 -r json
```

## Diagnostics

### inspect

Every enrichment writes a row to `enrichment_runs` with the routing decision (tier, model, host, token count), per-step timings, status, and the full conduit trace (including the actual rendered prompt that hit the model and a redacted echo of the input). `siphon inspect` reads that row for a given URI.

```bash
siphon inspect "youtube:///abc123XYZ"          # human-readable panel + trace table
siphon inspect "article:///sha256/..." --json  # raw JSON for LLM consumption
```

Pure Postgres read, no LLM call, no headwater hop.

Two intended use cases:

1. **Dev loop while iterating on guidelines or routing.** Run inspect after re-enriching a URI, diff against earlier traces (by `guideline_hash`), confirm the change is producing what you expect.
2. **Forensic mode.** When a summary looks wrong, `siphon inspect <uri> --json | pbcopy`, paste it into an LLM, and ask "why is this output bad?" The trace carries the rendered prompt, so the LLM has enough context to diagnose without needing to see the underlying code.

## Ingestion

### gulp

Active ingestion. Persists the result to the database.

```bash
siphon gulp "https://www.youtube.com/watch?v=K8NMuIRlyUI"
siphon gulp "./paper.pdf" -r s        # only print the summary
siphon gulp "@clipboard"              # ingest current clipboard
echo "raw text" | siphon gulp         # ingest piped stdin
```

`-r` / `--return-type` controls what gets printed after ingest (same codes as `query`).

### sync

Bulk ingestion for an Obsidian vault. Performs client-side change detection so only new or significantly modified notes get re-processed.

```bash
siphon sync --vault ~/vaults/main --concurrency 10
```

### extract / enrich / parse

Pipeline offramps that return intermediate results without persisting. Useful for one-shot processing without committing to the database.

```bash
siphon extract "./paper.pdf"   # raw text + metadata
siphon enrich  "./paper.pdf"   # extract then LLM-enrich
siphon parse   "./paper.pdf"   # just resolve to a URI
```

## Programmatic use

`SiphonClient` exposes the same retrieval surface as the CLI.

```python
from siphon_client.client import SiphonClient
from siphon_api.enums import SourceType

client = SiphonClient()

# Hybrid retrieval with HyDE (default)
results = client.search(
    query="claude code subagents",
    mode="hybrid",
    source_type=SourceType.YOUTUBE,
    limit=10,
)
for r in results.to_list():
    print(r.title, r.uri)

# Skip HyDE for a faster, keyword-shaped query
results = client.search(query="useState", mode="hybrid", use_hyde=False)
```

The `Collection[ProcessedContent]` return type supports functional chaining (`map`, `filter`, `flatmap`, `group_by`, `take`, `first`, `count`). See `siphon_client.collections.collection`.

## Environment

The client connects directly to Postgres (no headwater hop for reads) and to a HeadwaterClient for embedding generation (`hybrid` / `semantic` modes need to embed the query). Required env vars:

| Variable | Purpose |
| :--- | :--- |
| `POSTGRES_USERNAME` | Postgres user |
| `POSTGRES_PASSWORD` | Postgres password |

Headwater connection details are picked up from the headwater client's own config.
