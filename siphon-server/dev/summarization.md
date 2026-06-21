# Siphon Enrichment — Architecture and Migration

Status as of 2026-06-01.

## TL;DR

Siphon delegates summarization to conduit's `RoutingSummarizer`, which routes by input
token count to a tested `SummarizationProfile` from `PRODUCTION_ROUTING`. Per-Siphon-source
guidance (the structural "what the output should look like") lives in a Siphon-side
`guideline.jinja2`, rendered with metadata at call time and handed to conduit as opaque
text via `_TextInput.guideline`. Conduit owns model + strategy; Siphon owns content
shape.

Description is a separate downstream concern. See `retrieval.md`.

## Current state by source type

| Source | Summary (RoutingSummarizer) | Description (HyDE one-shot over summary) |
|---|---|---|
| article | yes (commit `040cfe3`) | yes (commit `83fbb23`) |
| arxiv | yes | yes |
| audio | yes | yes |
| doc | yes (per-variant) | yes (per-variant) |
| drive | n/a — `NotImplementedError` stub | n/a |
| email | yes | yes |
| github | yes | yes |
| image | yes | yes |
| obsidian | yes | yes |
| podcasts | n/a — no `enricher.py` | n/a |
| video | yes | yes |
| youtube | yes | yes |

All implemented enrichers now run the full new pipeline: summary via `RoutingSummarizer + PRODUCTION_ROUTING`, then description as a HyDE-shaped gpt-oss/bywater one-shot over the summary, then title (where the title is LLM-derived from description). Per-source description guidelines live at `sources/<source>/description_guideline.jinja2`; doc's per-variant guidelines at `sources/doc/<variant>_description_guideline.jinja2`.

`drive` and `podcasts` are not migrated because there is no enrichment code to migrate — drive's enricher raises `NotImplementedError`, podcasts has no `enricher.py`. Both need upstream work before the summarization migration applies.

## Canonical enricher shape (article = template)

```python
from conduit.strategies.summarize.strategy import _TextInput
from conduit.strategies.summarize.summarizers.routing import (
    PRODUCTION_ROUTING,
    RoutingSummarizer,
)

class ArticleEnricher(EnricherStrategy):
    def __init__(self):
        self.prompt_loader = PromptLoader(base_dir=PROMPTS_DIR)
        self.guideline_template = Prompt(GUIDELINE_PATH.read_text())

    async def enrich(self, content, preferred_model=PREFERRED_MODEL):
        text = content.text
        metadata = content.metadata
        # ... title extraction ...

        # parallel: description (downstream of summary, see retrieval.md) and summary
        description_task = self._describe(...)        # see retrieval.md
        summary_task = self._summarize(text, metadata)
        description, summary = await asyncio.gather(description_task, summary_task)

        return EnrichedData(...)

    async def _summarize(self, text, metadata):
        guideline = self.guideline_template.render({"metadata": metadata})
        text_input = _TextInput(data=text, source_id="article", guideline=guideline)
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})
```

Key boundaries:

- **Conduit handles**: token counting, tier selection, strategy execution, chunking,
  format-pass logic. The strategy's published config (model, host, chunk size, etc.)
  is held in `PRODUCTION_ROUTING` and treated as an eval-tested artifact.
- **Siphon handles**: source-specific guidance (the guideline template), metadata
  interpolation, raw-text extraction. Source-type knowledge stays Siphon-side.
- **`preferred_model` arg** is preserved on the protocol but **ignored for the summary
  path** (routing picks the model). It still honors the description path until that
  also migrates per `retrieval.md`.

## Per-source guideline files

Convention:

- `siphon-server/src/siphon_server/sources/<source>/guideline.jinja2` for templated
  guidelines (most cases, since metadata varies per document).
- `siphon-server/src/siphon_server/sources/<source>/guideline.md` for static
  guidelines with no per-document interpolation (uncommon).

The guideline should describe **what the final summary should look like**, including
the structural form, content emphasis, and source-specific constraints. It should
NOT include `{{text}}` because conduit's strategy templates own text injection.

Example structure (from `article/guideline.jinja2`):

```
[role framing: "You are an editor producing a human-readable summary..."]
[section: required output structure]
[section: constraints — neutral tone, no external knowledge, length targets]
[output format spec — markdown skeleton]
<metadata>
{{metadata}}
</metadata>
```

## Migration template for the other 10 source types

For each non-article enricher:

1. Identify the legacy "summary prompt" file (e.g., `sources/arxiv/prompts/arxiv_summary.jinja2`).
2. Strip the `<text>{{text}}</text>` block; everything else becomes `guideline.jinja2` in
   the same source folder.
3. Rewrite `<Source>Enricher.enrich()` to follow the article template above:
   - Description path stays as-is *until* the retrieval.md redesign also lands. Then it
     becomes a one-shot pass over the summary.
   - Summary path uses `RoutingSummarizer + PRODUCTION_ROUTING` with the rendered
     guideline.
4. Smoke-test against a representative document of that source type. Confirm tier
   selection matches expectation and the output follows the guideline structure.
5. Leave the legacy `*_summary.jinja2` file on disk unreferenced. Trivial cleanup later.

**Order of rollout** (recommendation, not locked):

1. **arxiv, doc, obsidian** — these are long-form. They will exercise Tier 2 / Tier 3
   regularly, validating that the format-pass logic produces usable summaries on real
   long documents.
2. **youtube, podcasts, audio** — transcripts can be very long; these are the strongest
   test of Tier 3.
3. **email, github** — usually short; Tier 1 path, low risk.
4. **video, image** — already use vision models; the summary path may need to differ.
   Address last.
5. **drive** — appears to be a thin dispatcher with no enrichment of its own. Verify
   before touching.

## Observability (in design as of 2026-06-21)

Motivating failure: the 32-min video `Kf0rPU7zy7Q` produced no summary, just hallucinated YouTube-outro boilerplate. Suspected root cause is the gpt-oss ECW cliff — quality 0.13 in the 5K–12K band that Tier 1 currently covers up to 12K. The failure was invisible until manual inspection. Goal: make this class of problem trivial to introspect.

### Layer 1 — persist conduit's trace (landed in code, pending deploy as of 2026-06-21)

RoutingSummarizer already emitted a trace; enrichers used to throw it away. Now wired in:

- Table `enrichment_runs` keyed by `(uri, enriched_at)`. Top-level queryable columns: `tier`, `strategy`, `token_count`, `model`, `host`, `status`, `duration_seconds`, `guideline_hash`, `error_message`. Full trace in `trace_json`. CHECK constraint on `status` accepts `success`, `model_error`, `timeout`, `empty_output`, `judge_rejected` (reserved for Layer 3, not emitted by v1).
- No `ProcessedContent.latest_enrichment_run_id` FK. Dropped during design — single-URI lookup is one shot via `WHERE uri = ? ORDER BY enriched_at DESC LIMIT 1` against the composite index, FK saves no queries. Failed runs may have no PC row at all, so the natural-key uri is the link.
- `guideline_hash` is `sha256(rendered_summary_guideline)[:16]`. Description guideline not hashed in v1.
- Conduit was widened with `rendered_prompt` metadata (OneShot's outgoing prompt, RollingRefine's per-chunk refine prompts, and the format-pass prompt) so the trace is forensic-grade, not timing-only.
- Trace redaction: `_TextInput.data` truncated to 2KB; RoutingSummarizer config `routing` field collapsed to profile names (full `PRODUCTION_ROUTING` is held in code). Outputs and rendered prompts preserved in full.
- CLI: `siphon inspect <uri>` (pure Postgres read, no headwater hop, no LLM call). Pretty-print default; `--json` for LLM consumption.

Implementation entry points:
- `siphon-server/src/siphon_server/core/enrichment_trace.py` — `capture_enrichment(uri=...)` async context manager and `register_guideline(rendered)` helper.
- `siphon-server/src/siphon_server/core/pipeline.py` — wraps `self.enricher.execute(...)` in `SiphonPipeline.process`.
- All 10 implemented enrichers call `register_guideline(guideline)` after rendering the summary guideline (article, arxiv, audio, doc, email, github, image, obsidian, video, youtube).
- `siphon-client/src/siphon_client/cli/inspect.py` — CLI subcommand.

Two intended use cases:
1. Dev loop while iterating on guidelines — diff traces across prompt revisions for the same URI.
2. Forensic mode — when a weird response surfaces, hand the trace (via `siphon inspect <uri> --json`) to an LLM and ask it to diagnose what happened.

Deploy gates: needs conduit + siphon on both hosts, then `python -m siphon_server.database.postgres.setup` on caruana to provision the table (idempotent `create_all`).

### Layer 2 — structural compliance check (rejected)

Considered and rejected. Deterministic regex over output structure (Executive Summary / Section Insights / Key Takeaways markers) would have caught the `Kf0rPU7zy7Q` failure immediately, but it locks the validator to the current guideline. Guidelines will evolve; the validator would accrue rewrite debt every time a section is renamed or restructured. Not worth it.

### Layer 3 — sampled LLM-judge on production ingests (TBD)

Nightly Cronicle job that samples a fraction of production `enrichment_runs` and re-scores with the Gemini3 judge already used in the conduit eval harness. Output: quality distribution over time, alarm when it drifts. Catches the class of failures Layer 1 can't (well-formed but semantically wrong output — e.g., on-topic-for-channel but wrong-for-this-video).

Not runtime (too heavy). Not in scope yet — defer until Layer 1 lands and there's a steady stream of `enrichment_runs` rows worth sampling.

## Cross-references

- Conduit eval and routing roadmap: `$BC/conduit-project/evals/STRATEGY.md`
- Siphon retrieval architecture (embedding, HyDE, RRF): `siphon-server/dev/retrieval.md`
- Routing decision (Tier 1/2/3, breakpoints, models, hosts): `conduit-project/evals/STRATEGY.md#published-routing-decision`
