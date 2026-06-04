# Siphon Retrieval — Embedding, HyDE, RRF

Status as of 2026-06-01. **Design locked, implementation pending.**

## TL;DR

Description becomes a retrieval-only artifact, robots-only, shaped to match
HyDE-generated hypothetical answers on the query side. It is generated as a one-shot
gpt-oss pass on top of the summary, not on raw text. The description, not
`(title, summary)`, is what gets embedded. The embedding model migrates from
`all-MiniLM-L6-v2` (384d, 256-token max) to `nomic-embed-text-v2`. Default query
search becomes RRF of vector retrieval and BM25 lexical retrieval; semantic-only
search remains available as a non-default option.

## What this changes

### Before

- `EnrichedData.description` is a "dense paragraph 90–180 words" written for humans
  with retrieval-optimized framing as a secondary concern. Generated in parallel
  with the summary from raw article text.
- `repository.get_embed_texts()` returns `(title, summary)` to the embed pipeline.
- Embedded artifact: concatenation of `title + summary`, silently truncated by
  all-MiniLM at 256 tokens (Executive Summary survives; Section Insights does not).
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`, 384 dims, 256-token
  sequence cap. Mid-tier on MTEB by 2026 standards.
- Query side: raw query embedded, cosine search via pgvector HNSW.

### After

- `EnrichedData.description` is a HyDE-shaped retrieval artifact. Answer-voice
  prose, no meta-commentary about the document, sized to fit the encoder.
  Generated as a one-shot pass on the summary (bounded input).
- `repository.get_embed_texts()` returns `{uri: description}` (single artifact).
- Embedded artifact: the description directly.
- Embedding model: `nomic-embed-text-v2`. 768 dims, 8K-token sequence cap.
  Already in use in the user's `blackglass` project for Obsidian vault embedding.
- Query side: HyDE-generated hypothetical answer embedded against description
  vectors; BM25 over `description + summary` as a parallel lexical signal;
  RRF fusion picks final ranking.

## Description prompt design principles

The description is no longer human-readable. It is shaped to land in the same
semantic territory as HyDE-generated hypotheticals so that vector retrieval
produces high-fidelity matches.

1. **No meta-commentary about the document.** Drop "This article describes,"
   "The piece argues," "The author claims." Start with content, not framing.
2. **Declarative answer voice.** Sentences should plausibly be the LLM's answer
   to "tell me about X." Not "the author claims Y," but "Y, because Z."
3. **Question-implied structure.** Every sentence should answer an implicit reader
   question. If you can't reverse-engineer the question, the sentence is descriptive
   overhead.
4. **Length to fit the encoder.** Target 130–180 words for nomic-embed-text-v2's
   8K-token window (well under cap, leaves room for richer description without
   truncation). Re-target if the encoder changes.
5. **Lexical-retrieval bonus, not requirement.** Preserve canonical entity names,
   dates, dollar amounts when possible. They help BM25 catch exact-match queries.
   But don't sacrifice answer-voice prose for verbatim preservation; pure vector
   retrieval doesn't care, and BM25 is a secondary signal in RRF.

### Sample contrast

Current article description (news-summary style, with meta-framing):

> "This analysis details a novel and reportedly 'unserious' zero-authentication
> method for exploiting major accounts on Instagram, noting that the vulnerability
> was active for weeks, if not months..."

HyDE-aligned rewrite (answer-voice, no meta-framing):

> "The Meta Instagram support AI can be manipulated into sending password reset
> codes to attacker-controlled emails. By claiming an account is hacked while
> using a proxy near the target's location, attackers bypass 2FA because resetting
> the password revokes all existing sessions. The vulnerability persisted for
> weeks before Meta patched it, after black-market Telegram groups were observed
> offering takeover services for high-value accounts..."

Same content, different semantic territory.

## Generation pipeline

```
content.text  ──►  RoutingSummarizer  ──►  summary (structured markdown, for humans)
                                              │
                                              ▼
                                   gpt-oss one-shot (bounded input)
                                   + description guideline (HyDE-shaped)
                                              │
                                              ▼
                                          description (retrieval artifact)
```

Sequential, not parallel. Description depends on summary. Cost: removes the
asyncio.gather concurrency between description and summary. Gain: bounded input
to gpt-oss eliminates the long-document ECW problem permanently, and the
description benefits from the summary's content distillation while still being
shaped independently for retrieval.

Description guideline lives at `siphon-server/src/siphon_server/sources/<source>/description_guideline.jinja2`.
Per-source variation expected: a youtube transcript description should differ from
an arxiv paper description, even at the answer-voice level.

## Embedding migration

### Model swap

| | Current | Target |
|---|---|---|
| Model | all-MiniLM-L6-v2 | nomic-embed-text-v2 |
| Dims | 384 | 768 |
| Max seq | 256 tokens | 8192 tokens |
| Year | 2021 | 2024 |
| MTEB retrieval (avg) | ~42 | ~58 |
| Hosted on | botvinnik (backwater) | botvinnik (backwater) |

### Source artifact swap

```python
# repository.py:265 — current
def get_embed_texts(...) -> dict[str, tuple[str, str]]:
    """Return {uri: (title, summary)} for URIs that need embedding."""

# target
def get_embed_texts(...) -> dict[str, str]:
    """Return {uri: description} for URIs that need embedding."""
```

### Schema migration

`models.py:11` — `EMBED_DIM = 384` becomes `EMBED_DIM = 768`. Comment update too.
HNSW index rebuilt on the new column. `embed_model` field already exists; populate
with the new model identifier so we can do per-model audits later.

### Re-embed all rows

After model + source-artifact swap, every existing row's embedding becomes invalid
(wrong dimension, wrong source). Embed-batch needs a `--force` pass to re-encode
all rows. Sequence:

1. Drop or rebuild the HNSW index for the new dimension.
2. NULL out existing `embedding` columns.
3. Run embed-batch over all rows. Since descriptions also need regeneration per
   the new prompt design, this is gated on description regeneration finishing first.

This is a one-shot migration. Cost is bounded by corpus size and backwater
encoder throughput.

## Query-side pipeline

### Three retrieval signals

| Signal | Source | Behavior |
|---|---|---|
| **HyDE vector** | gpt-oss-generated hypothetical answer to query, embedded | High recall on natural-language queries; tolerant of phrasing variance |
| **Raw vector** | Query text embedded directly | Cheaper (no LLM call); reasonable on short keyword queries |
| **BM25 lexical** | Postgres FTS over `description + summary` | Catches exact entity/number/quote matches that semantic encoding loses |

### Default: RRF fusion of HyDE + BM25

[Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
combines rankings without requiring score calibration:

```
score(doc) = sum over signals s of: 1 / (k + rank_s(doc))
```

`k = 60` is the standard constant. Top-N by combined score is the default result set.

Why RRF over weighted sum: pgvector cosine distance and BM25 scores are not on
comparable scales. RRF needs only the *ordering* from each signal, not the values.
Robust to one signal returning noisy scores.

### Non-default modes

- **`--semantic-only`** — skip BM25; vector-only retrieval. Useful when query is
  conceptual and lexical noise hurts.
- **`--bm25-only`** — skip vector; lexical-only. Useful for exact-entity queries
  where vector retrieval drifts.
- **`--no-hyde`** — embed raw query instead of generating a hypothetical. Faster,
  lower quality on conversational queries.

### HyDE generation prompt

Standard HyDE shape (Gao et al. 2022):

```
Write a passage that would answer the following question:

{{ query }}

The passage should be one to three paragraphs, factually framed, in answer voice.
Do not preface with "Here is..." or "The passage is...". Return only the passage.
```

Hypothetical is generated by gpt-oss/bywater (cheapest fast model). Embedded with
the same nomic-embed-text-v2 used for storage; query and corpus must share the
embedding model.

### Cost / latency

HyDE adds one LLM call per query (~1–3s with gpt-oss on bywater). Acceptable for
default interactive retrieval. For high-volume programmatic access, `--no-hyde`
falls back to raw-query embedding (no LLM call).

## Implementation phases

### Phase R1: description redesign (Siphon side) — DONE

- [x] Authored `description_guideline.jinja2` for article (HyDE-shaped, answer-voice, lean principles-only).
- [x] Rewrote `ArticleEnricher._describe()` to call gpt-oss/bywater one-shot on
  `(summary, rendered description_guideline)`, not raw text.
- [x] `enrich()` chains description after summary sequentially; asyncio.gather removed.
- [x] Smoke-tested against `0xsid.com/blog/meta-account-takeover-fiasco`. Description
  output is answer-voice, preserves canonical entities (@obamawhitehouse, $1.5T valuation),
  no meta-framing. Length ~190 words, inside the hard ceiling.

### Phase R2: embedding model + source artifact swap

- [ ] Confirm nomic-embed-text-v2 is reachable via backwater (it's already used by
  blackglass per the user's note).
- [ ] Update `EMBED_DIM = 768` in `models.py`. Update comment.
- [ ] Rewrite `get_embed_texts()` to return description only.
- [ ] Drop and rebuild HNSW index for 768-dim vectors.
- [ ] NULL out all `embedding` columns.

### Phase R3: re-embed all rows

- [ ] Regenerate descriptions for all stored rows (gated on Phase R1 landing).
- [ ] Run embed-batch with `--force` over all rows.
- [ ] Spot-check retrieval against known-good queries.

### Phase R4: query pipeline rewrite

- [ ] Implement HyDE generator (one gpt-oss call per query).
- [ ] Add Postgres FTS index on `description + summary` for BM25.
- [ ] Implement RRF fusion in the query layer.
- [ ] Add `--semantic-only`, `--bm25-only`, `--no-hyde` flags to the query CLI.
- [ ] Update the query history schema if it needs to capture the signal mix used.

### Phase R5: rollout to other 10 source types

Once Article validates the full description redesign + embedding flow, the other
10 enrichers migrate per `summarization.md`'s rollout order, each with its own
`description_guideline.jinja2`.

## Open questions

1. **Per-source description guidelines, or one shared?** Article-vs-arxiv-vs-podcast
   may need different answer-voice framings (a podcast description is answering
   different questions than a paper description). Start per-source; promote to
   shared if patterns converge.
2. **Description regeneration trigger.** When the description prompt changes, all
   stored descriptions are stale. Need a versioning or hash mechanism so embed-batch
   knows what to regenerate. Could fold into the existing `embed_model` field by
   making it a `(embed_model, description_version)` pair.
3. **HyDE model choice.** gpt-oss is fast and "good enough" for hypothetical
   generation, but if HyDE quality bottlenecks retrieval, gemma4 may be worth the
   latency. Worth measuring on a real query set after R4 lands.
4. **Hybrid retrieval at the SourceType level.** Some sources (github, email) may
   benefit from BM25-heavy retrieval; others (podcasts, video) from vector-heavy.
   RRF treats signals equally. A per-source weighting could help but adds tuning
   surface.

## Cross-references

- Siphon enrichment architecture: `siphon-server/dev/summarization.md`
- Conduit eval and routing roadmap: `$BC/conduit-project/evals/STRATEGY.md`
- Current embedding schema: `siphon-server/src/siphon_server/database/postgres/models.py`
- Current embedding repository ops: `siphon-server/src/siphon_server/database/postgres/repository.py:265-313`
- nomic-embed-text-v2 reference usage: blackglass project (Obsidian vault embeddings)
- HyDE paper: Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels," 2022
- RRF paper: Cormack, Clarke, Buettcher, SIGIR 2009
