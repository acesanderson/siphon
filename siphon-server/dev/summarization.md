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

## Cross-references

- Conduit eval and routing roadmap: `$BC/conduit-project/evals/STRATEGY.md`
- Siphon retrieval architecture (embedding, HyDE, RRF): `siphon-server/dev/retrieval.md`
- Routing decision (Tier 1/2/3, breakpoints, models, hosts): `conduit-project/evals/STRATEGY.md#published-routing-decision`
