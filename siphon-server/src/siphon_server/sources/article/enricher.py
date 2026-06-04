from siphon_server.config import settings
from siphon_api.interfaces import EnricherStrategy
from siphon_api.models import ContentData, EnrichedData
from siphon_api.enums import SourceType
from typing import override, Any
from pathlib import Path
import logging

from conduit.core.model.model_remote import RemoteModelAsync
from conduit.domain.request.generation_params import GenerationParams
from conduit.config import settings as conduit_settings
from conduit.strategies.summarize.strategy import _TextInput
from conduit.strategies.summarize.summarizers.routing import (
    PRODUCTION_ROUTING,
    RoutingSummarizer,
)

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.CRITICAL + 10)

GUIDELINE_PATH = Path(__file__).parent / "guideline.jinja2"
DESCRIPTION_GUIDELINE_PATH = Path(__file__).parent / "description_guideline.jinja2"

# HyDE-shaped description is a bounded one-shot pass on the summary.
# gpt-oss on bywater is the cheapest fast model and the input is always
# small (summary is at most a few thousand tokens), so we pin it here
# rather than route. If this ever needs to vary by source, lift to a
# Siphon-side config.
_DESCRIPTION_MODEL = "gpt-oss:latest"
_DESCRIPTION_HOST = "bywater"

PREFERRED_MODEL = settings.default_model


class ArticleEnricher(EnricherStrategy):
    """
    Enrich Article content with LLM.

    Summary path: RoutingSummarizer + PRODUCTION_ROUTING. Routes by token
    count to a tested SummarizationProfile. Guideline is rendered from
    guideline.jinja2 and passed as _TextInput.guideline.

    Description path: HyDE-shaped retrieval artifact. Generated as a one-shot
    gpt-oss/bywater pass on the summary (not raw text), shaped by
    description_guideline.jinja2. Sequential after summary because it depends
    on the summary as input. See siphon-server/dev/retrieval.md.
    """

    source_type: SourceType = SourceType.ARTICLE

    def __init__(self):
        from conduit.core.prompt.prompt import Prompt

        self.guideline_template = Prompt(GUIDELINE_PATH.read_text())
        self.description_guideline_template = Prompt(
            DESCRIPTION_GUIDELINE_PATH.read_text()
        )

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        logger.info("Enriching Article content")
        text = content.text
        metadata = content.metadata
        _ = content.metadata.pop("raw_text", None)
        title = content.metadata["title"]
        logger.info(f"Using existing title: {title}")

        # Sequential: description depends on summary.
        summary = await self._summarize(text, metadata)
        description = await self._describe(summary, metadata)

        logger.info("Generated summary and description")
        return EnrichedData(
            source_type=SourceType.ARTICLE,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )

    async def _summarize(self, text: str, metadata: dict[str, Any]) -> str:
        guideline = self.guideline_template.render({"metadata": metadata})
        text_input = _TextInput(data=text, source_id="article", guideline=guideline)
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})

    async def _describe(self, summary: str, metadata: dict[str, Any]) -> str:
        guideline = self.description_guideline_template.render({"metadata": metadata})
        prompt = f"{guideline}\n\n<summary>\n{summary}\n</summary>"
        model = RemoteModelAsync(model=_DESCRIPTION_MODEL, host_alias=_DESCRIPTION_HOST)
        params = GenerationParams(model=_DESCRIPTION_MODEL)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")
        result = await model.query(query_input=prompt, params=params, options=options)
        return str(result.content)


if __name__ == "__main__":
    import asyncio
    from siphon_server.sources.article.parser import ArticleParser
    from siphon_server.sources.article.extractor import ArticleExtractor

    article_url = "https://0xsid.com/blog/meta-account-takeover-fiasco"
    parser = ArticleParser()
    source_info = parser.parse(article_url)
    extractor = ArticleExtractor()
    content_data = extractor.extract(source_info)
    enricher = ArticleEnricher()

    enriched_data = asyncio.run(enricher.enrich(content_data))
    print("=== TITLE ===")
    print(enriched_data.title)
    print("\n=== DESCRIPTION ===")
    print(enriched_data.description)
    print("\n=== SUMMARY ===")
    print(enriched_data.summary)
